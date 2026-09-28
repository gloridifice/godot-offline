# 执行任务

首轮发现的 F1/F2 已修复，修复回归 33/33 通过。Windows 编辑器构建、CLI、OpenGL/Vulkan 和编辑器启动已实测；Present、MCP 等必测项仍未完成。所有任务保持未勾选，不能按部分通过勾选完整验收任务。

详细命令、环境、矩阵与复现证据见 [验收记录](acceptance.md)。

## 当前进度

### 已完成的实现草案

- 在 `OS` 增加进程级 offline 状态和平台初始化入口；Windows 实现申请并清理 `ProcessPowerThrottling` 执行速度覆盖，失败记录 Win32 错误。
- 在 Main 增加 `--offline` 帮助、解析、Windows 平台限制以及与 headless、Dummy、`--wid`、独占全屏的冲突检查，并将参数纳入工具/项目子进程转发范围。
- 在 `DisplayServerWindows` 增加隐藏模式门控草案：移除 `WS_VISIBLE`，限制显示、激活、焦点、鼠标捕获/裁剪/warp、独占全屏、进程嵌入和若干原生交互入口。
- 离线模式下，Windows alert 改为日志；文件对话框按取消返回；其他原生对话框和若干可见系统 UI 返回不可用。

### 已修复的验收缺陷

- F1：有效 headless 检查移到 `setup()` 中、服务层扩展注册之前；三条原崩溃路径均正常退出 1，无扩展清理或泄漏错误。
- F2：offline 原生样式移除 `WS_MINIMIZE`，保留 Godot 逻辑最小化及不可绘制状态；两后端的初始最小化、连续两次最小化恢复均通过，恢复后的尺寸和图像有效。

### 尚未完成或待复核
- 原生嵌入 feature 在隐藏运行时返回 false；GameView、EditorRun 的实际子进程/重启和偏好保持仍未验收，不能仅由 feature 查询推导通过。
- 已新增[测试入口及夹具](../../../../../tests/platform/windows/offline/run_acceptance.py)，包括确定性 2D/3D 场景、启动前窗口监控和图像断言；Camera2D、隔离夹具、策略单元测试及失败注入执行仍缺失。源码已有 `TESTS_ENABLED` 限定的 HighQoS 失败注入入口，本轮未启用它。
- 尚未构建模板或 .NET 编辑器；PresentMon 退出码 1 且没有 CSV，实际 Present 证据仍缺失。MCP 三种截图工具均未调用。

### 构建与实测

- `python -m SCons platform=windows target=editor dev_build=yes use_mingw=yes d3d12=no accesskit=no -j8`：本轮已完成链接，退出码 0。
- 默认 D3D12/AccessKit 依赖仍缺失，本轮未验证这些配置；ANGLE 也缺少依赖。
- 修复回归：CLI 21/21；OpenGL 与 Vulkan 各 5/5（含新增初始最小化）；隐藏编辑器和 Project Manager 启动 2/2。完整矩阵与未测范围见验收记录。
- 本轮仅修复 F1/F2、强化回归测试并更新记录，没有自动提交或推送。

## 1. 验证环境与夹具

- [ ] 1.1 固定 Windows 图形环境、.NET 构建链和 Godot-MCP 测试版本
  - Design: [基线与环境](implement.md#6-verification-and-documentation-impact)
  - Acceptance: 核对本仓库 Mono 构建要求与插件依赖，记录选定 commit/tag、SDK、GPU/驱动、可用后端、测试项目和本地 MCP 连接方式；不把依赖装进引擎运行时，不静默修改全局 MCP 配置。环境受阻时记录实际原因，保持未完成。见 [M1](specs/mcp-screenshot-compatibility.md#m1-连接与可见基线)。

- [ ] 1.2 增加确定性场景夹具、窗口监控和图像断言入口
  - Dependencies: 1.1
  - Design: [验证方案](implement.md#6-verification-and-documentation-impact)
  - Acceptance: 夹具包含 2D/3D 视图、Camera2D/Camera3D、隔离目标及非目标标记，可切换明显不同的画面状态。监控在目标进程创建前开始，记录显示事件、可见 HWND、前台 PID、客户区尺寸与退出；图像可解码并验证内容变化。运行产物与源夹具分离。见 [S2](specs/offline-window-mode.md#s2-窗口生命周期)、[M5](specs/mcp-screenshot-compatibility.md#m5-证据与回归)。

## 2. 引擎实现

- [ ] 2.1 实现 `--offline` 解析、平台状态和 HighQoS 生命周期
  - Blocked: none
  - Verification: F1 已修复并复测；HighQoS 失败和清理仍待验收。
  - Design: [API 与生命周期](implement.md#3-apis-and-data-model)、[启动解析](implement.md#41-启动解析)
  - Acceptance: 帮助及无值参数生效，重复幂等，用户参数区不影响模式；显式/隐含 headless、dummy、wid 冲突顺序无关。非 Windows 拒绝。HighQoS 在首个图形初始化前申请，失败非零退出并带 Win32 错误；正常/失败清理释放覆盖，普通模式不受影响。见 [S1](specs/offline-window-mode.md#s1-启动与参数)、[S4](specs/offline-window-mode.md#s4-highqos-与失败)、[S6](specs/offline-window-mode.md#s6-回归与平台边界)。

- [ ] 2.2 实现 Windows 原生窗口显示、样式、模式及输入副作用门控
  - Blocked: none
  - Verification: F2 已修复并复测；其他未覆盖窗口路径仍需验证。
  - Dependencies: 2.1
  - Design: [窗口算法](implement.md#42-原生显示门控)
  - Acceptance: 创建、回退重建、样式修改、最大化/普通全屏/恢复、换屏和子窗口均不闪窗；不抢前台、裁剪或移动桌面鼠标。维护有效几何与逻辑模式，保留原有非最小化可绘制性；不调用 Window.hide 或替换渲染目标。独占全屏明确拒绝。见 [S2](specs/offline-window-mode.md#s2-窗口生命周期)、[S3](specs/offline-window-mode.md#s3-绘制与截图基础)、[S6](specs/offline-window-mode.md#s6-回归与平台边界)。

- [ ] 2.3 处理非交互错误与原生对话框请求
  - Dependencies: 2.1
  - Design: [原生交互](implement.md#43-原生交互和错误)
  - Acceptance: 初始化/窗口创建错误没有 MessageBox；致命错误仍非零退出，普通 alert 只记录日志。原生文件选择异步取消一次，其他原生对话框返回 ERR_UNAVAILABLE 且不调用结果回调。无未处理模态等待，无普通模式回归。见 [S4](specs/offline-window-mode.md#s4-highqos-与失败)、[S5](specs/offline-window-mode.md#s5-子进程与交互)。

- [ ] 2.4 接入编辑器子进程、重启参数继承并禁用离线游戏嵌入
  - Dependencies: 2.1, 2.2
  - Design: [进程传播](implement.md#44-编辑器进程传播)
  - Acceptance: EditorRun、Project Manager 和编辑器重启传播模式，但不传播用户参数区的同名参数；游戏为独立隐藏子进程，父进程不再注入 wid、嵌入显示或创建临时焦点窗口。持久化 embed-on-play 偏好不变，各子进程独立申请 HighQoS。见 [S5](specs/offline-window-mode.md#s5-子进程与交互)。

## 3. 实际验证

- [ ] 3.1 完成 CLI/策略单元测试与 Windows 原生图形集成验证
  - Blocked: Present 证据缺失；模板、子进程和其他失败路径仍未完成，F1/F2 已修复。
  - Dependencies: 1.2, 2.1, 2.2, 2.3, 2.4
  - Design: [渲染边界](implement.md#45-渲染与截图)、[验证方案](implement.md#6-verification-and-documentation-impact)
  - Acceptance: 构建普通 Windows 编辑器与模板，执行 [S1–S6](specs/offline-window-mode.md#acceptance-scenarios)。覆盖仅测试可用的 HighQoS 失败注入、初始化错误、窗口操作及参数组合。项目主场景/指定场景均输出新帧内部截图和实际图形提交/Present 证据，所有本机可用后端记录实际选择及回退。没有 offline 时正常显示、嵌入和 headless 的基线不回归；不能用 mock 测试代替 GPU/窗口实测。

- [ ] 3.2 构建修改后的 .NET 编辑器并取得 MCP 可见运行基线
  - Dependencies: 1.1, 1.2, 2.1, 2.2, 2.3, 2.4
  - Design: [MCP 环境规格](specs/mcp-screenshot-compatibility.md#r1-环境与基线)
  - Acceptance: 按 modules/mono/README.md 生成对应 glue/程序集，插件加载到包含本变更的 .NET 二进制。通过实际 MCP tool discovery 核对 schema，三种工具可见基线有效，记录实参和 PNG；关闭基线进程，避免下一阶段连接旧会话。完成 [M1](specs/mcp-screenshot-compatibility.md#m1-连接与可见基线)。

- [ ] 3.3 使用实际 MCP 验证隐藏编辑器 2D/3D viewport 截图
  - Dependencies: 3.1, 3.2
  - Design: [viewport 场景](specs/mcp-screenshot-compatibility.md#m2-隐藏-2d3d-viewport)
  - Acceptance: 以 offline 参数启动并核对 MCP 所连目标 PID，真实调用 screenshot-viewport 获取 2D 和 3D 图像；解码、查看并断言预期内容，修改标记后重拍验证新鲜度，窗口监控全程无显示。至少一个真实后端通过；不可用环境/工具必须标阻塞。完成 [M2](specs/mcp-screenshot-compatibility.md#m2-隐藏-2d3d-viewport)、[M5](specs/mcp-screenshot-compatibility.md#m5-证据与回归) 对应记录。

- [ ] 3.4 使用实际 MCP 验证指定相机与节点隔离截图
  - Dependencies: 3.1, 3.2
  - Design: [相机](specs/mcp-screenshot-compatibility.md#m3-指定相机)、[隔离](specs/mcp-screenshot-compatibility.md#m4-节点隔离)
  - Acceptance: 真实调用 screenshot-camera 和 screenshot-isolated；验证请求尺寸、相机取景、目标存在和非目标排除。改变内容后重拍，确认没有旧帧或遗留场景副作用；检查临时资源清理和无闪窗。保存 PNG、工具参数与窗口证据，不用其他截图脚本替代。完成 [M3–M5](specs/mcp-screenshot-compatibility.md#acceptance-scenarios)。

## 4. 文档与最终验证

- [ ] 4.1 同步实际交付的当前架构与契约
  - Dependencies: 3.1, 3.3, 3.4
  - Acceptance: 更新 doco/architecture.md，新增 doco/specs/windows-offline-mode.md，内容仅包含实际交付的启动、平台边界、错误和截图兼容性。明确原有节能/重绘策略及不承诺性能等价；记录已测后端和 MCP 兼容性边界，不复制实现流水账。

- [ ] 4.2 完成整体回归、证据核验与交付汇总
  - Dependencies: 4.1
  - Acceptance: 重跑相关测试及 doco check，逐项对照 proposal 和两份目标规格；列出实测矩阵、未测范围、命令/退出码及 MCP 三种工具结论，清理本次测试服务/子进程。确认未修改普通模式策略、用户持久化偏好或全局 MCP 配置。仍有必测项阻塞时不得宣称全部完成；本任务不自动授权执行 doco complete/archive。

## Verification

创建阶段曾执行：

- `doco list --no-interactive`：退出码 0，无同目标活动变更。
- `doco new windows-offline-hidden-window --no-interactive`：成功创建 full package。
- 已检查当前架构、相关源代码及 Window/mock 测试；Godot-MCP 要求依据上游 README 和截图工具说明，实际版本和 schema 留待实施时固定。

- `doco check windows-offline-hidden-window --no-interactive`：创建阶段通过，退出码 0；当时 12 项任务尚未完成。
- 相对 Markdown 链接、标题锚点和模板占位符检查：创建阶段通过。

暂停前实施阶段执行：

- `git diff --check`：通过，无空白错误。
- 默认 Windows 编辑器构建：因本机缺少 Direct3D 12 SDK 和 AccessKit 依赖而停止。
- `scons platform=windows target=editor dev_build=yes use_mingw=yes d3d12=no accesskit=no -j8`：编译已推进，但在最终链接和退出码产生前按要求中止；结果记为未完成，不记为通过。
- 未执行 GUI/GPU 运行、窗口可见性监控、模板构建、.NET 构建、MCP 连接或截图调用，也未安装插件。

首轮验收新增执行：

- Windows 编辑器构建：退出码 0；`run_acceptance.py --group cli`：退出码 1（18/21）；`--group graphics --backend opengl3` / `vulkan`：均退出码 1（各 3/4）；`--group editor`：退出码 0（2/2）。完整命令和证据见 [acceptance.md](acceptance.md)。
- 同后端可见/隐藏内部 PNG 像素一致，标记从红变绿；已用 read 查看可见基线和隐藏截图。隐藏用例无目标显示/前台事件，运行期 HighQoS 为 `ControlMask=1, StateMask=0`。
- PresentMon 尝试失败，无 CSV；未执行任何 MCP 截图，不将普通内部截图冒充 MCP 通过。
- 测试脚本的 `py_compile` 检查、记录验收文档前的 `git diff --check`：通过。
- 首轮文档更新后的最终检查曾因 Git Bash 启动故障无法执行，与 F1 引擎失败分开记录。本轮 shell 已能执行命令。

F1/F2 修复回归执行：

- 同选项增量构建：退出码 0，约 200 秒。
- `run_acceptance.py --group all --backend opengl3`：退出码 0，28/28；`--group graphics --backend vulkan`：退出码 0，5/5。命令及新旧证据位置见 [acceptance.md](acceptance.md)。
- 拒绝路径正常退出；初始和重复最小化时 `Window.can_draw()` 为 false，恢复后为 true，客户区与 PNG 尺寸正确。隐藏用例无目标显示/前台事件，两后端恢复后的 PNG 已查看。
- 修改的两份 C++ 文件通过 `clang-format --dry-run --Werror`；测试脚本通过 `py_compile`；`git diff --check` 通过。
- `doco check windows-offline-hidden-window --no-interactive`：机械检查通过；完整任务仍未完成，Present 等验收缺口保持记录。

所有任务继续保持未勾选；编译成功与部分用例通过不代表完整窗口、失败清理、Present 或 MCP 验收通过。
