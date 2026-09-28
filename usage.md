# 编译与使用 Windows offline 模式

本仓库的 `--offline` 参数让 Godot 在隐藏原生窗口的同时，继续使用正常的 Windows 图形路径运行编辑器或项目。它保留真实窗口、渲染设备和 Viewport，适合需要内部截图但不希望显示窗口的自动化任务。

**offline 不代表断网，也不等同于 `--headless`。** 音频、网络仍按项目配置工作，运行时仍需要可用的 GPU 和图形驱动。该参数仅支持 Windows；请使用本仓库编译的程序，不要替换成官方发行版。

当前已验证 Windows x86_64 的 MinGW 编辑器构建，以及 OpenGL/Vulkan 隐藏运行和内部截图。导出模板、编辑器运行游戏的子进程、.NET/Godot-MCP 和主交换链 Present 采集尚未完成验收。

## 1. 准备编译环境

以下命令在 **Windows PowerShell** 中执行。先进入本仓库根目录，即包含 `SConstruct` 的目录：

```powershell
# 替换为你的源码路径。
Set-Location "C:\src\godot-offline"
```

准备这些工具，并将可执行文件所在目录加入 `PATH`：

- Python 3.9 或更新版本；已验证 Python 3.11。
- SCons 4.4 或更新版本。
- 64 位 MinGW-w64 工具链，GCC 11 或更新版本，包含 `gcc`、`g++`、`ar`、`windres`；已验证 GCC 15.2。
- 支持 OpenGL 3.3 或 Vulkan 的显卡及驱动，用于运行编译后的程序。

安装 SCons 并检查工具：

```powershell
python -m pip install "scons>=4.4"
python --version
python -m SCons --version
gcc --version
g++ --version
windres --version
```

这里使用 MinGW，不要求安装 Visual Studio。其他工具链的准备方法见 [Godot Windows 编译文档](https://docs.godotengine.org/en/latest/engine_details/development/compiling/compiling_for_windows.html)。本文不涉及 C#/.NET 构建。

## 2. 编译可执行文件

在 Windows x86_64 环境执行已验证的构建命令：

```powershell
python -m SCons platform=windows target=editor dev_build=yes use_mingw=yes d3d12=no accesskit=no -j8
if ($LASTEXITCODE -ne 0) { throw "Godot 编译失败，请检查上方日志。" }
```

参数说明：

| 参数 | 用途 |
|---|---|
| `platform=windows target=editor` | 构建 Windows 编辑器；同一程序也可以直接运行项目或指定场景 |
| `dev_build=yes` | 开启开发调试构建，便于诊断；生成文件较大 |
| `use_mingw=yes` | 使用 MinGW，即使已安装 MSVC |
| `d3d12=no accesskit=no` | 不编入 Direct3D 12 和 AccessKit，避免这两项额外依赖；仍可使用 OpenGL/Vulkan |
| `-j8` | 最多 8 个并行构建任务；内存不足时可改为 `-j4` 或 `-j2` |

若提示缺少 ANGLE 依赖，可在命令中追加 `angle=no`，明确禁用 ANGLE；本文的运行命令不使用它。D3D12、AccessKit、ANGLE 的关闭是这套构建配置的选择，并非 offline 模式的必要条件。

成功后，`bin/` 中会生成：

```text
bin/godot.windows.editor.dev.x86_64.exe
bin/godot.windows.editor.dev.x86_64.console.exe
```

前者是引擎程序，后者是控制台包装器。包装器会启动同目录的引擎、转发参数和日志，并等待退出，因此两者要放在一起。后续命令用包装器，方便在 PowerShell 中观察日志和退出码；`--offline` 隐藏的是 Godot 窗口，不会隐藏你正在使用的终端。

不需要开发调试构建时，可改用 `dev_build=no`。对应文件名不再包含 `.dev`，后续 `$Godot` 路径也要调整；该配置未纳入当前验收。

## 3. 使用 `--offline`

先设置程序和项目路径。`$Project` 应指向包含 `project.godot` 的目录：

```powershell
$Godot = (Resolve-Path ".\bin\godot.windows.editor.dev.x86_64.console.exe").Path
$Project = "C:\projects\MyGame"

# 确认使用的是带 offline 支持的构建。
& $Godot --help | Select-String -SimpleMatch -Pattern "--offline"
```

每条运行命令都会等待程序退出。隐藏编辑器或长期运行的项目不会因没有可见窗口而自动结束；建议首次检查时加上下一节的 `--quit-after`。

### 隐藏运行项目主场景

```powershell
& $Godot --offline --path $Project --rendering-method gl_compatibility --rendering-driver opengl3
```

项目需要已设置主场景。首次运行或资源需要重新导入时，可以先完成一次隐藏导入：

```powershell
& $Godot --offline --editor --import --path $Project --rendering-method gl_compatibility --rendering-driver opengl3
```

### 隐藏运行指定场景

将 `res://scenes/demo.tscn` 替换为项目中的场景路径：

```powershell
& $Godot --offline --path $Project --scene "res://scenes/demo.tscn" --rendering-method gl_compatibility --rendering-driver opengl3
```

### 隐藏启动编辑器

```powershell
& $Godot --offline --editor --path $Project --rendering-method gl_compatibility --rendering-driver opengl3
```

这只启动编辑器，不会自动运行项目。当前不要将编辑器启动成功视为 F5/F6、游戏子进程或重启链路均已验证；自动化运行项目时可直接使用前面的独立进程命令。

### 使用 Vulkan / Forward+

```powershell
& $Godot --offline --path $Project --rendering-method forward_plus --rendering-driver vulkan
```

以上显式指定后端，便于复现。也可以省略 `--rendering-method` 和 `--rendering-driver`，使用项目配置。实际选中的后端与 GPU 以启动日志为准。

## 4. 自动退出、日志与截图

启动后运行有限次主循环迭代，再退出并查看日志：

```powershell
$Log = Join-Path $env:TEMP "godot-offline.log"
& $Godot --offline --path $Project --rendering-method gl_compatibility --rendering-driver opengl3 --quit-after 120 --verbose --log-file $Log
$ExitCode = $LASTEXITCODE
Get-Content $Log
"Godot exit code: $ExitCode"
```

`--quit-after 120` 是迭代次数，不是 120 秒，也不保证生成 120 张截图。长期任务应由脚本在完成后调用 `get_tree().quit()`；退出被阻塞时，可在任务管理器中定位本次启动的进程，不要批量结束其他 Godot 实例。

offline 不会自动保存截图。项目脚本应等待 `RenderingServer.frame_post_draw`，再通过 Viewport 纹理读取图像并保存；可以参考[验收场景脚本](tests/platform/windows/offline/fixture/main.gd)。不要用桌面截屏判断隐藏 Viewport 的内容，也不要为了截图恢复或显示原生窗口。

### 参数与运行限制

- 将 `--offline` 放在 `--` 或 `++` 用户参数分隔符之前；其后的同名参数只交给项目，不会启用隐藏模式。
- 不能与 `--headless`、`--display-driver headless`、Dummy 渲染器/渲染驱动或 `--wid` 混用，调整顺序也不能绕过检查。
- 项目配置为 headless、包含 `dedicated_server` 特征，或工具参数隐含 headless（如 `--doctool`）时，同样不能使用 offline。
- 不支持独占全屏。若项目以独占全屏启动，应先改为窗口化，或在命令中加 `--windowed`。
- 原生文件选择请求自动按取消返回；原生消息/输入对话框不可用，`OS.alert()` 改为日志。不要让自动化任务等待这些交互。
- 启动时必须成功申请 Windows HighQoS 策略；失败会记录 Win32 错误并非零退出，不会静默降级为 headless。
- 隐藏不会强制最大帧率：现有低处理器模式、VSync 和音频行为保持不变，不保证与可见窗口性能相同。显式最小化仍会暂停窗口绘制，需要出图时不要将窗口设为最小化。

## 5. 运行自检

自检需要 Windows 桌面会话和 Pillow，使用引擎 `.exe`，而不是控制台包装器。下列命令会分别执行 OpenGL 全组及 Vulkan 图形组测试；图形组会短暂显示一个正常窗口作为对照，其余隐藏用例由外部监控检查可见性。

```powershell
python -m pip install Pillow
$Engine = (Resolve-Path ".\bin\godot.windows.editor.dev.x86_64.exe").Path
$Output = Join-Path $env:TEMP ("godot-offline-check-" + [guid]::NewGuid().ToString("N"))

python tests/platform/windows/offline/run_acceptance.py --godot $Engine --output "$Output-opengl" --group all --backend opengl3
if ($LASTEXITCODE -ne 0) { throw "OpenGL/CLI/编辑器自检失败，查看 $Output-opengl。" }

python tests/platform/windows/offline/run_acceptance.py --godot $Engine --output "$Output-vulkan" --group graphics --backend vulkan
if ($LASTEXITCODE -ne 0) { throw "Vulkan 自检失败，查看 $Output-vulkan。" }
```

输出目录必须尚不存在；重新运行时重新生成 `$Output`。检查各目录中的 `summary.json`，以及各用例的 `run.json`、`stdout.log` 和 PNG。脚本会复制独立测试项目，不要求运行你自己的项目。

自检通过只说明这些用例通过，不能代替模板、编辑器子进程、Present 或 MCP 验收。需要 C# 或 Godot-MCP 时，另按 [Mono 构建说明](modules/mono/README.md) 准备 .NET 编辑器与程序集；本文编译的普通编辑器不包含这些能力。
