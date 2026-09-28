# 验收记录

## 结论

**F1/F2 已修复，修复回归 33/33 通过；整体验收仍未完成。** Present、模板、编辑器子进程及 .NET/MCP 等未测项不因本轮通过而视为完成。未执行 complete/archive。

## F1/F2 修复回归

### 修复范围

- `main/main.cpp`：在 `setup()` 注册项目显示驱动设置后检查有效驱动，拒绝隐式 headless；不再从已注册服务层扩展的 `setup2()` 返回到只清理核心层的错误路径。命令行选择仍优先于项目设置。
- `platform/windows/display_server_windows.cpp`：offline 样式移除 `WS_MINIMIZE`，避免原生最小化清空客户区，而受门控的 ShowWindow 无法恢复它。Godot 的逻辑 minimized 状态及 `window_can_draw()` 判定不变。
- 测试强化：拒绝路径检查无扩展清理/泄漏错误；新增初始最小化启动与恢复，连续两次显式最小化/恢复，并断言 `Window.can_draw()` 在最小化时为 false、恢复后为 true。外部监控同时检查原生最小化样式位。

### 构建及复测

- 基线 `536d909fe5` 加本轮未提交修复；构建选项与首轮相同，退出码 0，耗时约 200 秒。
- 修复后二进制 SHA-256：`affe4792ff9bafb803599882fd6f7cef6bdc552a732f94baf4bb8f8afd27737c`。
- 证据位于原根目录的 `fixes-01/`：`build.log`、`build-result.json`、`opengl-final/summary.json`、`vulkan-final/summary.json` 及各用例的命令、窗口状态、日志、PNG。

```powershell
python tests/platform/windows/offline/run_acceptance.py --godot bin/godot.windows.editor.dev.x86_64.exe --output "$env:TEMP/godot-offline-acceptance/fixes-01/opengl-final" --group all --backend opengl3
python tests/platform/windows/offline/run_acceptance.py --godot bin/godot.windows.editor.dev.x86_64.exe --output "$env:TEMP/godot-offline-acceptance/fixes-01/vulkan-final" --group graphics --backend vulkan
```

以上两条命令均退出 0，重跑时需改用新的输出目录。

| 修复回归 | 结果 |
|---|---|
| CLI，包括三条原先崩溃的隐式 headless 路径 | 21/21；拒绝路径正常退出 1，无扩展清理/泄漏错误 |
| OpenGL 图形与生命周期 | 5/5 |
| Vulkan 图形与生命周期 | 5/5 |
| 隐藏编辑器、Project Manager 启动 | 2/2 |

恢复后客户区及 PNG 均为 `720×520`；初始最小化恢复后为 `640×480`。已读取两后端恢复后的 PNG，蓝色方块和绿色标记正常。所有隐藏用例未检测到显示/前台事件，未添加原生最小化样式；Godot 逻辑最小化仍禁止绘制。所有测试子进程已退出并回收。

以下保留首轮失败证据，避免用复测结果覆盖原始复现。

## 首轮构建与环境

- 源码：`536d909fe5c1521a8b61455975fd22fccd397404`。
- Windows 11 企业版，build `26200`；GPU：NVIDIA GeForce RTX 3070，Windows 驱动 `32.0.16.1088`（图形日志 `610.88`）。
- Python `3.11.15`、SCons `4.10.1`、MinGW GCC `15.2.0`、Pillow `12.3.0`。
- 构建命令：`python -m SCons platform=windows target=editor dev_build=yes use_mingw=yes d3d12=no accesskit=no -j8`。
- 构建退出码 **0**，耗时约 26 分钟。二进制：`bin/godot.windows.editor.dev.x86_64.exe`。
- 二进制 SHA-256：`8506036cdc6af8662dfed37e4d4de2e1ee663ba884bae6fb933dc71a969374a0`。
- 实测后端：OpenGL 3.3 Compatibility、Vulkan 1.4.341 Forward+。D3D12/AccessKit 未编入；构建还提示缺少 ANGLE 依赖，未测试 ANGLE。
- .NET SDK：`9.0.318`、`10.0.302`；有 .NET 8 runtime，但没有 .NET 8 SDK。本轮未构建 Mono 编辑器或托管程序集，不能据此判断插件兼容性。

## 测试入口与证据

新增入口：`tests/platform/windows/offline/run_acceptance.py`，场景源位于同目录 `fixture/`。

入口会复制测试项目到新的输出目录，并在启动进程前安装 WinEvent SHOW/FOREGROUND hook；循环 EnumWindows/EnumChildWindows，记录目标 PID、可见位、客户区、前台和光标裁剪区域。外部监控进程启用 DPI awareness，避免把逻辑像素误当客户区物理尺寸。进程退出码、命令、检查结果、原生窗口状态和 PNG 分开保存。

场景包含红色/绿色 2D 标记和固定相机下的蓝色 3D 方块。图像检查同时验证尺寸、标记颜色、方块存在和内容更新；窗口生命周期每一步另检查有效客户区与图像尺寸。此夹具不是 MCP 相机/隔离工具的替代品。

本机证据根目录：`C:/Users/linyifan05/AppData/Local/Temp/godot-offline-acceptance/`。目录为运行产物，不提交 Git；源码夹具可重跑。

| 目录/文件 | 内容 |
|---|---|
| `build.log`、`build-result.json` | 完整构建日志及退出码 |
| `environment.json` | 系统、GPU、SDK、编译器信息 |
| `cli-02/summary.json` | 修正测试配置后的 21 个 CLI 用例 |
| `gl-02/summary.json` | OpenGL 4 个图形用例 |
| `vulkan-01/summary.json` | Vulkan 4 个图形用例 |
| `editor-01/summary.json` | 隐藏编辑器和无项目 Project Manager 启动 |
| `gl-01/` | 首轮可见窗口 cutty 检查、内部 PNG、PresentMon 尝试 |
| `round-1-summary.json` | 汇总、图像对照和进程检查 |

重跑示例（输出目录必须尚不存在）：

```powershell
python tests/platform/windows/offline/run_acceptance.py --godot bin/godot.windows.editor.dev.x86_64.exe --output "$env:TEMP/offline-cli-recheck" --group cli
python tests/platform/windows/offline/run_acceptance.py --godot bin/godot.windows.editor.dev.x86_64.exe --output "$env:TEMP/offline-gl-recheck" --group graphics --backend opengl3
python tests/platform/windows/offline/run_acceptance.py --godot bin/godot.windows.editor.dev.x86_64.exe --output "$env:TEMP/offline-vulkan-recheck" --group graphics --backend vulkan
python tests/platform/windows/offline/run_acceptance.py --godot bin/godot.windows.editor.dev.x86_64.exe --output "$env:TEMP/offline-editor-recheck" --group editor
```

`--capture-visible` 只对可见基线调用 cutty。本轮已读取可见窗口 PNG，以及隐藏 OpenGL/Vulkan 的内部 PNG；能看到蓝色方块和红→绿标记。隐藏窗口没有交给 cutty 捕获，因为该工具可能临时恢复窗口。编辑器测试使用相同二进制的自包含副本与独立设置目录，不改用户编辑器偏好。

## 首轮实测矩阵

| 项目 | 结果 | 边界 |
|---|---|---|
| 显式 headless/display-headless/dummy-method/dummy-driver/wid，正反顺序 | 10/10 通过 | 正常退出码 1，有 offline 诊断，无窗口 |
| 后续参数覆盖已出现的冲突项 | 3/3 通过 | 不因最终参数覆盖而绕过冲突 |
| 隐式工具/headless 配置/dedicated-server 特征 | 0/3，失败 | 拒绝后发生 `0xC0000005`，见 F1 |
| 项目 dummy 和初始独占全屏 | 2/2 通过 | 正常退出码 1，无窗口 |
| `--`、`++` 后的 offline 用户参数及帮助 | 3/3 通过 | 用户参数保留；headless 无图形适配器；帮助不建窗口 |
| OpenGL 可见、隐藏主场景、隐藏指定场景 | 3/3 通过 | 640×480、预期内容与更新；不等于已验证 Present |
| Vulkan 可见、隐藏主场景、隐藏指定场景 | 3/3 通过 | 实际选择 RTX 3070 / Vulkan；不等于已验证 Present |
| 最大化/窗口化/普通全屏、无边框、调整尺寸、原生子窗口 | 已执行的检查通过 | 两个后端均未发现显示事件或抢前台；不包含换屏、后端回退、编辑器布局恢复 |
| 显式最小化再恢复 | 两后端均失败 | 客户区 `0×0`、图像 `2×2`，见 F2 |
| 原生文件选择、options 文件选择 | 已执行的检查通过 | 主线程异步各取消一次，`false`、空列表、回调形状正确 |
| 原生消息/输入对话框、OS.alert | 已执行的检查通过 | `ERR_UNAVAILABLE`、无结果回调；alert 写日志并返回 |
| 隐藏编辑器、无项目 Project Manager | 2/2 启动检查通过 | 未测试 F5/F6、重启或布局恢复 |
| HighQoS 运行期状态 | 两后端均读取成功 | `ControlMask=1, StateMask=0`；时序、失败注入及清理仍未验收 |

修正夹具后的主用例矩阵共 31 项，26 通过、5 失败；5 个失败对应 F1 的 3 条启动路径和 F2 的 2 个后端。该计数不涵盖未运行的完整验收项目。

同一后端下，可见/隐藏模式的 `a.png`、`b.png` 像素一致。所有本轮隐藏用例的监控均未记录目标窗口显示或抢前台；可见基线能记录显示事件，确认监控确实工作。这只覆盖本轮场景和运行时间，不代表所有窗口入口已经审计完成。

### F1：隐式 headless 拒绝后异常退出

- 复现：`--offline --doctool <dir>`；或项目 `display/display_server/driver.windows="headless"`；或测试项目顶层 `_custom_features="dedicated_server"`。
- 三条路径均打印 `--offline cannot use the headless display driver.`，随后报 `deinitialize_extensions` 等级条件错误并有 ObjectDB 泄漏警告；实际退出码 `3221225477`（`0xC0000005`），不是正常拒绝的退出码 1。
- 监控未发现原生窗口。未把“崩溃也是非零”当作通过。
- 定位入口：`main/main.cpp:3297` 的 `setup2()` 提前返回及上层 `setup()` 错误清理。建议把有效配置检查移到能安全回滚的初始化阶段，或补齐该阶段对应的清理；具体崩溃栈尚未调试确认。
- Resolved: 本轮三条复现路径已正常拒绝并退出 1；其他 S4 失败注入与清理项目仍未验收。

### F2：隐藏窗口最小化恢复后尺寸丢失

- 复现：隐藏启动 → 窗口调整到 `720×520` → 显式最小化 → 恢复窗口化。
- OpenGL 与 Vulkan 的 `DisplayServer.window_get_mode()` 都恢复为窗口化，但 Window 客户区为 `0×0`，后续 Viewport 图像为 `2×2`，无法维持预期内容。
- 定位入口：`platform/windows/display_server_windows.cpp` 的 `window_set_mode()`、`_update_window_style()` 和 `WM_WINDOWPOSCHANGED`。建议检查禁用原生 ShowWindow 后的最小化状态及恢复矩形维护，不通过显示窗口规避。
- Resolved: 本轮两后端的初始最小化及重复最小化恢复均通过；S2/S3 的其他未测项保持待验收。

## 尚未取得的证据

- **Present：** 使用本机 NVIDIA FrameViewSDK 的 `PresentMon_x64.exe`，为每个目标指定独立 ETW session，未请求提权或停止既有 session。工具退出码 1、没有 CSV，也没有解释原因的输出；单独 1 秒探测同样如此。原因待查，不能推断为权限错误，也不能用截图替代主交换链 Present 证据。
- **MCP：** 候选测试版本固定为 Godot-MCP `v0.25.1` / `e2e0789e0bc082b21075806cac3db090e83244ab`；已核对该版本 README、csproj 和服务器版本常量：.NET 8、Godot.NET.Sdk 最低 4.3.0、ReflectorNet 5.4.1、McpPlugin 8.6.0、服务器 9.2.9。仅核对上游源码，未安装插件、未启动服务、未发现实际 schema、未调用三个截图工具。4.8-dev 兼容性待实际构建确认。
- 未构建导出模板、Mono 编辑器或 `tests=yes` 二进制；源码已有仅 `TESTS_ENABLED` 可用的 HighQoS 失败注入分支，但没有执行该分支。
- 未验证 HighQoS 的申请时序与释放、真实 GPU 初始化失败、非 Windows 拒绝、编辑器子进程/重启、普通原生对话框/嵌入回归，以及完整 MCP 2D/3D/相机/隔离语义。
- 脚本未监控编辑器后代进程，因此不能以当前编辑器启动结果覆盖 S5。

## 后续顺序

1. 补全缺失的窗口操作、HighQoS 失败/清理、编辑器子进程和模板验证；另解决 Present 采集入口。
2. 在独立项目完成 .NET 构建及固定版本 MCP 的可见/隐藏对照。
3. 只有全部必测项通过后，才更新当前规格并考虑完成变更。

本轮 Godot 测试进程均已 wait 回收；PresentMon 探测也已退出。进程检查发现的复用 PID 属于其他程序，未对它们执行终止。未修改全局 MCP 配置，未提交或推送本轮新增文件。

首轮测试脚本的 `py_compile` 和记录文档前的 `git diff --check` 已通过；当时最终 `doco check` / Git 检查被 Git Bash 的 `fatal error - add_item ... failed, errno 1` 阻塞。本轮命令已能执行，修复源码的 `clang-format --dry-run --Werror`、测试脚本 `py_compile` 和 `git diff --check` 均已通过；`doco check windows-offline-hidden-window --no-interactive` 机械检查通过，仍提示未完成任务和剩余验收阻塞。这类 shell 启动故障与 F1 的引擎失败分开记录。
