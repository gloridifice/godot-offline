#!/usr/bin/env python3
"""Windows/GPU integration checks; not a replacement for Godot-MCP acceptance.

Requires Python 3.10+ and Pillow. Uses a copy of the fixture and keeps all runtime
artifacts outside the checkout. WinEvent hooks are installed before each launch.
Only processes started here are terminated on timeout. Hidden windows are never
restored or captured through desktop capture APIs.
"""

import argparse
import csv
import ctypes as ct
from ctypes import wintypes as wt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from PIL import Image, ImageChops


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


class WindowMonitor:
    def __init__(self):
        self.user = ct.WinDLL("user32", use_last_error=True)
        self.kernel = ct.WinDLL("kernel32", use_last_error=True)
        self.event_type = ct.WINFUNCTYPE(None, wt.HANDLE, wt.DWORD, wt.HWND, wt.LONG, wt.LONG, wt.DWORD, wt.DWORD)
        self.enum_type = ct.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        signatures = {
            "SetWinEventHook": (wt.HANDLE, [wt.DWORD, wt.DWORD, wt.HMODULE, self.event_type, wt.DWORD, wt.DWORD, wt.DWORD]),
            "UnhookWinEvent": (wt.BOOL, [wt.HANDLE]),
            "GetWindowThreadProcessId": (wt.DWORD, [wt.HWND, ct.POINTER(wt.DWORD)]),
            "EnumWindows": (wt.BOOL, [self.enum_type, wt.LPARAM]),
            "EnumChildWindows": (wt.BOOL, [wt.HWND, self.enum_type, wt.LPARAM]),
            "GetForegroundWindow": (wt.HWND, []),
            "IsWindowVisible": (wt.BOOL, [wt.HWND]),
            "GetWindowLongPtrW": (ct.c_ssize_t, [wt.HWND, ct.c_int]),
            "GetClientRect": (wt.BOOL, [wt.HWND, ct.POINTER(wt.RECT)]),
            "GetClipCursor": (wt.BOOL, [ct.POINTER(wt.RECT)]),
            "GetWindowTextW": (ct.c_int, [wt.HWND, wt.LPWSTR, ct.c_int]),
            "GetClassNameW": (ct.c_int, [wt.HWND, wt.LPWSTR, ct.c_int]),
            "PeekMessageW": (wt.BOOL, [ct.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT, wt.UINT]),
            "TranslateMessage": (wt.BOOL, [ct.POINTER(wt.MSG)]),
            "DispatchMessageW": (ct.c_ssize_t, [ct.POINTER(wt.MSG)]),
        }
        for name, (result, args) in signatures.items():
            fn = getattr(self.user, name)
            fn.restype, fn.argtypes = result, args
        for name, result, args in [
            ("OpenProcess", wt.HANDLE, [wt.DWORD, wt.BOOL, wt.DWORD]),
            ("CloseHandle", wt.BOOL, [wt.HANDLE]),
            ("GetProcessInformation", wt.BOOL, [wt.HANDLE, ct.c_int, wt.LPVOID, wt.DWORD]),
        ]:
            fn = getattr(self.kernel, name)
            fn.restype, fn.argtypes = result, args
        self.pid = None
        self.events = []
        self.states = {}
        self.foreground_hits = 0
        self.clip_changes = []
        self.qos = None
        self.samples = 0
        self.hooks = []
        self.clip_before = self.clip()
        self.started = time.monotonic()
        self.callback = self.event_type(self.event)
        for minimum, maximum in [(0x8002, 0x8002), (3, 3)]:
            hook = self.user.SetWinEventHook(minimum, maximum, None, self.callback, 0, 0, 0)
            if not hook:
                self.close()
                raise ct.WinError(ct.get_last_error())
            self.hooks.append(hook)

    def owner(self, hwnd):
        pid = wt.DWORD()
        self.user.GetWindowThreadProcessId(hwnd, ct.byref(pid))
        return pid.value

    def clip(self):
        rect = wt.RECT()
        self.user.GetClipCursor(ct.byref(rect))
        return [rect.left, rect.top, rect.right, rect.bottom]

    def event(self, hook, event, hwnd, object_id, child_id, thread_id, timestamp):
        if hwnd and self.owner(hwnd) == self.pid and (event == 3 or object_id == 0):
            self.events.append({"event": event, "hwnd": int(hwnd), "time_ms": timestamp})

    def pump(self):
        message = wt.MSG()
        while self.user.PeekMessageW(ct.byref(message), None, 0, 0, 1):
            self.user.TranslateMessage(ct.byref(message))
            self.user.DispatchMessageW(ct.byref(message))

    def poll(self):
        self.pump()
        self.samples += 1
        if self.owner(self.user.GetForegroundWindow()) == self.pid:
            self.foreground_hits += 1
        clip = self.clip()
        if clip != self.clip_before and clip not in self.clip_changes:
            self.clip_changes.append(clip)

        @self.enum_type
        def visit(hwnd, unused):
            if self.owner(hwnd) == self.pid:
                rect = wt.RECT()
                self.user.GetClientRect(hwnd, ct.byref(rect))
                title, class_name = ct.create_unicode_buffer(512), ct.create_unicode_buffer(128)
                self.user.GetWindowTextW(hwnd, title, len(title))
                self.user.GetClassNameW(hwnd, class_name, len(class_name))
                state = {"hwnd": int(hwnd), "visible": bool(self.user.IsWindowVisible(hwnd)),
                         "style_visible": bool(self.user.GetWindowLongPtrW(hwnd, -16) & 0x10000000),
                         "style_minimized": bool(self.user.GetWindowLongPtrW(hwnd, -16) & 0x20000000),
                         "size": [rect.right - rect.left, rect.bottom - rect.top],
                         "title": title.value, "class": class_name.value}
                self.states[json.dumps(state, sort_keys=True)] = state
            return True

        @self.enum_type
        def top(hwnd, unused):
            visit(hwnd, unused)
            if self.owner(hwnd) == self.pid:
                self.user.EnumChildWindows(hwnd, visit, 0)
            return True

        self.user.EnumWindows(top, 0)
        # Read actual process policy while the graphics window exists. This does
        # not prove ordering relative to initialization or cleanup on exit.
        if self.states and self.qos is None:
            handle = self.kernel.OpenProcess(0x1000, False, self.pid)
            if handle:
                try:
                    state = (wt.DWORD * 3)(1, 0, 0)
                    ok = self.kernel.GetProcessInformation(handle, 4, state, ct.sizeof(state))
                    self.qos = {"ok": bool(ok), "version": state[0], "control": state[1], "state": state[2],
                                "error": 0 if ok else ct.get_last_error()}
                finally:
                    self.kernel.CloseHandle(handle)

    def report(self):
        states = list(self.states.values())
        return {"pid": self.pid, "samples": self.samples, "events": self.events,
                "windows": states, "foreground_hits": self.foreground_hits,
                "clip_before": self.clip_before, "clip_changes": self.clip_changes, "qos": self.qos,
                "native_hidden": not self.events and not self.foreground_hits and not any(
                    state["visible"] or state["style_visible"] for state in states)}

    def close(self):
        for hook in self.hooks:
            self.user.UnhookWinEvent(hook)
        self.hooks.clear()


def run_case(binary, project, out, name, args, hidden=True, timeout=45, capture=False, presentmon=None):
    directory = out / name
    directory.mkdir()
    command = [str(binary), "--path", str(project), *args]
    environment = dict(os.environ, GODOT_OFFLINE_TEST_OUTPUT=str(directory))
    monitor = WindowMonitor()
    process = None
    expired = False
    desktop_capture = None
    present_process = None
    present_log = None
    present_command = None
    started = time.monotonic()
    try:
        with (directory / "stdout.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(command, cwd=directory, env=environment, stdout=log,
                                       stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            monitor.pid = process.pid
            if presentmon:
                present_log = (directory / "presentmon.log").open("w", encoding="utf-8")
                present_command = [str(presentmon), "--process_id", str(process.pid),
                                   "--session_name", "GodotOfflineAcceptance_" + str(process.pid),
                                   "--output_file", str(directory / "present.csv"), "--no_console_stats",
                                   "--timed", "12", "--terminate_after_timed"]
                present_process = subprocess.Popen(present_command, stdout=present_log, stderr=subprocess.STDOUT,
                                                   creationflags=subprocess.CREATE_NO_WINDOW)
            while process.poll() is None:
                monitor.poll()
                if capture and desktop_capture is None and (directory / "b.png").exists():
                    # Only the explicitly visible baseline may use cutty: it can
                    # restore hidden windows and would invalidate hidden tests.
                    result = subprocess.run(["cutty", "--pid", str(process.pid), "-r", "min(0.5x, 540s)"],
                                            capture_output=True, text=True, timeout=10)
                    desktop_capture = {"exit_code": result.returncode, "path": result.stdout.strip(),
                                       "stderr": result.stderr.strip()}
                if time.monotonic() - started > timeout:
                    expired = True
                    process.kill()
                    break
                time.sleep(0.01)
            process.wait(timeout=10)
            monitor.poll()
    finally:
        if process and process.poll() is None:
            process.kill()
            process.wait()
        monitor.close()
        if present_process:
            try:
                present_process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                present_process.kill()
                present_process.wait()
        if present_log:
            present_log.close()
    result = {"name": name, "command": command, "exit_code": process.returncode, "timeout": expired,
              "elapsed_seconds": round(time.monotonic() - started, 2), "monitor": monitor.report(),
              "capture": desktop_capture}
    if present_process:
        rows = []
        if (directory / "present.csv").exists():
            with (directory / "present.csv").open(encoding="utf-8-sig", newline="") as stream:
                rows = [row for row in csv.DictReader(stream) if row.get("ProcessID") == str(process.pid)]
        result["presentmon"] = {"command": present_command, "exit_code": present_process.returncode,
                                "target_rows": len(rows), "first_rows": rows[:2]}
    if (directory / "result.json").exists():
        result["fixture"] = json.loads((directory / "result.json").read_text(encoding="utf-8"))
    result["hidden_expected"] = hidden
    save(directory / "run.json", result)
    return result


def image_checks(directory):
    with Image.open(directory / "a.png") as original, Image.open(directory / "b.png") as updated:
        a, b = original.convert("RGB"), updated.convert("RGB")
        red, green, cube = a.getpixel((60, 60)), b.getpixel((60, 60)), b.getpixel((320, 240))
        difference = ImageChops.difference(a, b)
        return {"size": a.size == b.size == (640, 480),
                "red_marker": red[0] > 220 and red[1] < 30 and red[2] < 30,
                "green_marker": green[1] > 220 and green[0] < 30 and green[2] < 30,
                "blue_cube": cube[2] > 180 and cube[2] > cube[0] * 1.5 and cube[2] > cube[1],
                "fresh_content": difference.getbbox() is not None,
                "samples": {"red": red, "green": green, "cube": cube}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="New directory outside the checkout")
    parser.add_argument("--group", choices=["cli", "graphics", "editor", "all"], default="all")
    parser.add_argument("--backend", choices=["opengl3", "vulkan"], default="opengl3")
    parser.add_argument("--capture-visible", action="store_true", help="Use cutty on the visible baseline only")
    parser.add_argument("--presentmon", type=Path, help="Optional PresentMon executable; never requests elevation")
    options = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Requires a Windows desktop session")
    # Prevent DPI virtualization of HWND client sizes in the external monitor.
    user32 = ct.WinDLL("user32", use_last_error=True)
    user32.SetProcessDpiAwarenessContext.argtypes = [wt.HANDLE]
    user32.SetProcessDpiAwarenessContext.restype = wt.BOOL
    if not user32.SetProcessDpiAwarenessContext(wt.HANDLE(-4)):
        raise ct.WinError(ct.get_last_error())
    binary, out = options.godot.resolve(), options.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    project = out / "project"
    shutil.copytree(Path(__file__).parent / "fixture", project)
    results = []

    def case(name, args, project_path=None, **kwargs):
        result = run_case(binary, project_path or project, out, name, args, **kwargs)
        results.append(result)
        return result

    def finish(result, assertions):
        result["assertions"] = assertions
        result["pass"] = all(assertions.values()) and not result["timeout"]
        save(out / "summary.json", results)
        print(json.dumps({"case": result["name"], "pass": result["pass"], "assertions": assertions,
                          "exit": result["exit_code"], "capture": result["capture"]}), flush=True)

    if options.group in ("cli", "all"):
        for conflict in [["--headless"], ["--display-driver", "headless"],
                         ["--rendering-method", "dummy"], ["--rendering-driver", "dummy"], ["--wid", "1"]]:
            for index, args in enumerate([["--offline", *conflict], [*conflict, "--offline"]]):
                result = case(conflict[0][2:] + str(index), args)
                log = (out / result["name"] / "stdout.log").read_text(encoding="utf-8", errors="replace")
                finish(result, {"rejected": result["exit_code"] == 1,
                                "diagnostic": "--offline" in log, "no_windows": not result["monitor"]["windows"],
                                "hidden": result["monitor"]["native_hidden"]})
        for name, args in [
            ("headless_overridden", ["--offline", "--headless", "--display-driver", "windows"]),
            ("display_overridden", ["--offline", "--display-driver", "headless", "--display-driver", "windows"]),
            ("dummy_overridden", ["--offline", "--rendering-method", "dummy", "--rendering-method", "gl_compatibility"]),
            ("implicit_tool", ["--offline", "--doctool", str(out / "docs")]),
        ]:
            result = case(name, args)
            log = (out / name / "stdout.log").read_text(encoding="utf-8", errors="replace")
            finish(result, {"rejected": result["exit_code"] == 1, "hidden": result["monitor"]["native_hidden"],
                            "diagnostic": "--offline" in log, "no_windows": not result["monitor"]["windows"],
                            "clean_shutdown": "deinitialize_extensions" not in log and "leaked at exit" not in log})
        settings = (project / "project.godot").read_text(encoding="utf-8")
        for name, original, replacement in [
            ("config_headless", "[display]", '[display]\ndisplay_server/driver.windows="headless"'),
            ("config_dummy", 'renderer/rendering_method="gl_compatibility"', 'renderer/rendering_method="dummy"'),
            ("config_dedicated", "config_version=5", 'config_version=5\n_custom_features="dedicated_server"'),
            ("config_exclusive", "[display]", "[display]\nwindow/size/mode=4"),
        ]:
            config_project = out / (name + "_project")
            shutil.copytree(Path(__file__).parent / "fixture", config_project)
            (config_project / "project.godot").write_text(settings.replace(original, replacement), encoding="utf-8")
            result = case(name, ["--offline"], project_path=config_project)
            log = (out / name / "stdout.log").read_text(encoding="utf-8", errors="replace")
            finish(result, {"rejected": result["exit_code"] == 1, "diagnostic": "--offline" in log,
                            "no_windows": not result["monitor"]["windows"], "hidden": result["monitor"]["native_hidden"],
                            "clean_shutdown": "deinitialize_extensions" not in log and "leaked at exit" not in log})
        for separator in ["--", "++"]:
            result = case("user_args_" + ("dash" if separator == "--" else "plus"), ["--headless", separator, "--offline"])
            fixture = result.get("fixture", {}).get("info", {})
            finish(result, {"exit_ok": result["exit_code"] == 0, "headless": fixture.get("display") == "headless",
                            "no_adapter": fixture.get("adapter") == "", "preserved": "--offline" in fixture.get("user_args", [])})
        result = case("help", ["--offline", "--help"])
        log = (out / "help" / "stdout.log").read_text(encoding="utf-8", errors="replace")
        finish(result, {"exit_ok": result["exit_code"] == 0, "help": "--offline" in log,
                        "no_windows": not result["monitor"]["windows"]})

    graphics = ["--rendering-method", "gl_compatibility" if options.backend == "opengl3" else "forward_plus",
                "--rendering-driver", options.backend]
    if options.group in ("graphics", "all"):
        minimized_project = out / "minimized_project"
        shutil.copytree(Path(__file__).parent / "fixture", minimized_project)
        settings = (minimized_project / "project.godot").read_text(encoding="utf-8")
        (minimized_project / "project.godot").write_text(
            settings.replace("[display]", "[display]\nwindow/size/mode=1"), encoding="utf-8")
        for name, flags in [("visible", []), ("hidden", ["--offline", "--offline"]),
                            ("scene", ["--offline", "--scene", "res://main.tscn"]),
                            ("lifecycle", ["--offline"]), ("initial_minimized", ["--offline"])]:
            user = ["--", "--exercise"] if name == "lifecycle" else []
            if name == "initial_minimized":
                user = ["--", "--restore-initial-minimized"]
            capture = name == "visible" and options.capture_visible
            if capture or options.presentmon:
                if not user:
                    user = ["--"]
                user.append("--hold")
            result = case(name, [*flags, *graphics, *user], hidden=name != "visible", timeout=90,
                          project_path=minimized_project if name == "initial_minimized" else None,
                          capture=capture, presentmon=options.presentmon)
            fixture = result.get("fixture", {})
            monitor = result["monitor"]
            assertions = {"exit_ok": result["exit_code"] == 0, "fixture_finished": bool(fixture),
                          "fixture_checks": all(item["pass"] for item in fixture.get("checks", [])),
                          "windows_driver": fixture.get("info", {}).get("display") == "Windows",
                          "requested_backend": fixture.get("info", {}).get("driver") == options.backend,
                          "native_window": any(s["class"] == "Engine" for s in monitor["windows"])}
            if options.presentmon:
                assertions["present_observed"] = result["presentmon"]["target_rows"] > 0
            if name == "visible":
                assertions["visible_baseline"] = any(s["visible"] for s in monitor["windows"])
            else:
                assertions["hidden"] = monitor["native_hidden"]
                assertions["native_not_minimized"] = not any(
                    state["style_minimized"] for state in monitor["windows"] if state["class"] == "Engine")
                assertions["cursor_unconfined"] = not monitor["clip_changes"]
                qos = monitor.get("qos") or {}
                assertions["high_qos"] = bool(qos.get("ok") and qos["control"] & 1 and not qos["state"] & 1)
                assertions["embedding_disabled"] = fixture.get("info", {}).get("embedding_available") is False
            try:
                images = image_checks(out / name)
                result["images"] = images
                assertions.update({key: value for key, value in images.items() if key != "samples"})
            except (OSError, ValueError) as error:
                result["image_error"] = str(error)
                assertions["images"] = False
            finish(result, assertions)

    if options.group in ("editor", "all"):
        # Self-contained copy prevents tests from writing the user's editor
        # settings, layouts or Project Manager registry.
        engine_dir = out / "engine"
        engine_dir.mkdir()
        isolated_binary = engine_dir / binary.name
        shutil.copy2(binary, isolated_binary)
        (engine_dir / "_sc_").touch()
        result = run_case(isolated_binary, project, out, "editor",
                          ["--offline", "--editor", *graphics, "--quit-after", "120"], timeout=120)
        results.append(result)
        finish(result, {"exit_ok": result["exit_code"] == 0, "native_window": bool(result["monitor"]["windows"]),
                        "hidden": result["monitor"]["native_hidden"]})
        empty_project = out / "empty_project"
        empty_project.mkdir()
        result = run_case(isolated_binary, empty_project, out, "project_manager",
                          ["--offline", *graphics, "--quit-after", "120"], timeout=120)
        results.append(result)
        finish(result, {"exit_ok": result["exit_code"] == 0, "native_window": bool(result["monitor"]["windows"]),
                        "hidden": result["monitor"]["native_hidden"]})
    return 0 if all(result["pass"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
