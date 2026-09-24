# Godot-MCP 隐藏运行截图验收

## Scope and current contracts

本文件规定实现后的外部集成验收，不表示已经连接或验证 Godot-MCP。依赖 [隐藏窗口目标规格](offline-window-mode.md)，不增加引擎截图 API。

测试对象是 [IvanMurzak/Godot-MCP](https://github.com/IvanMurzak/Godot-MCP) 的 `screenshot-viewport`、`screenshot-camera`、`screenshot-isolated`。上游 README 和 [截图工具说明 PR](https://github.com/IvanMurzak/Godot-MCP/pull/15) 表明：viewport 工具读取编辑器 Viewport；camera 工具使用共享相机世界的 SubViewport；isolated 工具在独立 World3D 中渲染节点。执行时以固定版本源码和实际 MCP tool schema 为准，不能凭本文猜测参数。

## Requirements

### R1 环境与基线

- 使用包含本变更的 Windows .NET/Mono 编辑器构建，不得用未修改的官方编辑器替代。引擎本身的 `--offline` 不依赖 Mono，仅此插件验收需要它。
- 当前上游要求 C#/.NET 版 Godot、.NET 8 SDK 与相应 NuGet 依赖；执行前核对选定插件版本及本分支 Godot.NET.Sdk 的实际要求，满足两者，不假定所有 4.x 版本自动兼容。
- 在独立测试项目安装并启用插件，固定 Godot-MCP commit/tag 和服务版本；连接本地 MCP，不向引擎资源目录或全局客户端配置静默安装依赖。
- 记录引擎 commit/构建选项、可执行文件路径、插件/服务版本、Windows/GPU/驱动、实际 renderer/backend、分辨率、项目配置以及运行命令。
- 先用同一二进制的可见模式建立基线，再使用 `--offline` 重做相同调用，两个进程不能混淆。必须确认 MCP 指向目标隐藏进程，不能复用仍连接到可见编辑器的会话。
- 在至少一个真实图形后端完成全套 MCP 测试。其他可用 Vulkan、D3D12、OpenGL/ANGLE 后端复测并记录；不可用项列出原因，不能计为通过或承诺已验证。

### R2 图像内容与新鲜度

- PNG 必须可解码，尺寸与当前工具请求/Viewport 对应，包含测试场景的已知标记或几何体，不能是空白、纯黑、全透明或上次运行残留。
- 使用确定性夹具：固定随机种子、相机、灯光、背景和尺寸；提供明显不同的 2D/3D 标记，以及用于隔离测试的非目标物体。必要的颜色管理差异在同一后端可见/隐藏对照中说明。
- 每条工具路径至少执行两次，中间改变预期可见的对象颜色、位置或标记；第二张图必须反映变更，不能只检查文件修改时间或 PNG 字节不同。
- `screenshot-viewport` 分别验证 2D 和 3D 编辑视图，测试前选择/激活相应编辑器视图并等待资源导入及实际渲染。
- `screenshot-camera` 验证相机取景、请求尺寸和内容，与编辑器自由视角作区分；按选定版本声明覆盖 Camera2D/Camera3D。
- `screenshot-isolated` 验证目标 Node3D 存在且夹具中的非目标物体未混入，并确认工具结束后编辑场景未被永久改写。

### R3 无临时显示与状态恢复

- 从隐藏进程启动开始持续监控窗口状态，三种截图及重复请求期间均不得显示、激活或临时恢复任何窗口。
- 保留插件既有请求/等待帧机制；隐藏模式不全局启用连续更新、不伪造前台焦点。场景变化后若工具一直等待新帧，必须定位并修复或记录阻塞，不能以显示窗口作为规避方案。
- 测试前后检查场景脏状态、相机/节点、临时 SubViewport/World 等资源及窗口状态。正常退出后不残留测试服务或子进程。
- 截图证据来自实际 MCP 请求返回的图像/文件，解码后查看内容并执行夹具断言。不能改用独立 GDScript 截图替代这三项验收。

## Boundaries, errors and compatibility

MCP 的 SubViewport 截图属于既有应用/插件功能，不是给 `--offline` 增加离屏替代目标。camera/isolated 成功不能证明主 HWND 的交换链和 Present 正常；该证据由 [S3 绘制验证](offline-window-mode.md#s3-绘制与截图基础) 单独提供。

截图产生 GPU 回读、编码与传输成本，不放入性能测量区间。本变更不要求跨后端逐像素相等，不以 FPS 相等为成功标准。

插件不兼容、缺少 .NET/GPU、MCP 无法连接或工具不可用时，记录实际错误与受阻范围，保留验收未完成。不能跳过后宣称本变更已经通过全部验收；需要缩减范围时另行取得用户同意。

## Acceptance scenarios

### M1 连接与可见基线

构建并启动修改后的 .NET 编辑器，导入测试项目，确认插件加载、三种工具可发现、schema 已核对。可见模式分别产生有效参考截图并记录工具实参，关闭该进程，确认后续连接不会命中旧会话。

### M2 隐藏 2D/3D viewport

以 `--offline --editor --path <fixture>` 启动，确认目标 PID 和后端；打开并激活 2D/3D 编辑视图，分别调用 `screenshot-viewport`，验证尺寸与内容。修改标记后重拍，确认新内容可见，原生窗口全程不可见。

### M3 指定相机

在同一隐藏编辑器中调用 `screenshot-camera`，使用指定 Camera2D/Camera3D 和所支持的尺寸参数；核对取景标记。改变相机或目标后重拍，验证更新，并确认编辑场景未留下工具副作用。

### M4 节点隔离

夹具含目标 Node3D 与显著的非目标物体；调用 `screenshot-isolated` 后只出现目标渲染。修改目标后重拍，图像相应改变，临时资源和场景状态在请求结束后恢复。

### M5 证据与回归

每项保留请求/响应摘要、实际参数、目标 PID、PNG、图像断言/查看结论和窗口监控结果。生成可见/隐藏、后端和工具结果矩阵。另运行隐藏场景的引擎内截图与提交验证；成功的编辑器 MCP 调用不能覆盖这一项。缺项明确标为未测或阻塞。

## Current-document impact

交付后在新增当前规格 doco/specs/windows-offline-mode.md 中记录已验证的 Viewport 截图兼容性及边界，在 proposal Result 中保留 MCP 版本与三种工具验收结论。具体工具 schema、临时 PNG 和运行日志留在测试产物，不作为引擎长期 API 契约。
