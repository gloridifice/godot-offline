# 实现设计

## 1. Baseline and goals

源码基线为 Godot 4.8-dev、`ca871ccc9c`。创建变更时工作区已有未跟踪的 .agents/、AGENTS.md 和 doco/ 初始化内容，无已发现的引擎源码改动；不将这些初始化文件算成本变更实现，也不覆盖它们。[当前架构](../../../../architecture.md)尚未记录实现边界，没有相关当前规格或有效 ADR。

目标行为以 [窗口模式规格](specs/offline-window-mode.md) 和 [MCP 截图规格](specs/mcp-screenshot-compatibility.md) 为准。

| 现有入口 | 已核对的行为与改动原因 |
|---|---|
| [main/main.cpp](../../../../../main/main.cpp)：参数解析、`setup()`、`setup2()` | `--headless` 选择 headless/Dummy；编辑器、场景共用 DisplayServer 创建；`--offline` 尚不存在。解析结束后、项目加载前可建立进程策略，之后仍需验证配置隐含的 headless/dummy。 |
| [core/os/os.h](../../../../../core/os/os.h)、[os.cpp](../../../../../core/os/os.cpp) | 已有运行状态、平台初始化接口及 Main 友元；没有 offline API。 |
| [platform/windows/os_windows.h](../../../../../platform/windows/os_windows.h)、[os_windows.cpp](../../../../../platform/windows/os_windows.cpp) | OS 对象覆盖启动失败与正常退出；`alert()` 直接 MessageBox；初始化已有 `timeBeginPeriod`。 |
| [platform/windows/display_server_windows.h](../../../../../platform/windows/display_server_windows.h)、[display_server_windows.cpp](../../../../../platform/windows/display_server_windows.cpp) | 主/子 HWND、显示和样式、模式变更、原生对话框、嵌入子进程均由此管理；可绘制性目前只检查 minimized。构造中应用 flag 也可能显示窗口。 |
| [scene/main/window.cpp](../../../../../scene/main/window.cpp) | `_make_window()`、`set_visible()` 管理逻辑可见性和 Viewport；不能借助这些方法隐藏原生窗口。 |
| [main/main.cpp](../../../../../main/main.cpp)：`iteration()` | 按可绘制性和既有低处理器模式调用 RenderingServer，保持此算法。 |
| [EditorNode](../../../../../editor/editor_node.cpp)、[EditorRun](../../../../../editor/run/editor_run.cpp)、[GameView](../../../../../editor/run/game_view_plugin.cpp)、[ProjectManager](../../../../../editor/project_manager/project_manager.cpp) | 工具/项目参数转发、编辑器重启和 `--wid` 注入；GameView 还会从父进程显示子进程 HWND。 |
| [RendererViewport](../../../../../servers/rendering/renderer_viewport.cpp)、[RendererCompositorRD](../../../../../servers/rendering/renderer_rd/renderer_compositor_rd.cpp) | 常规 Viewport 先绘制，再合成到屏幕交换链，支持内部纹理回读；不新增替代路径。 |
| [Vulkan driver](../../../../../drivers/vulkan/rendering_device_driver_vulkan.cpp)、[D3D12 driver](../../../../../drivers/d3d12/rendering_device_driver_d3d12.cpp) | Vulkan 交换链 `clipped=true`，D3D12 使用 flip-discard 和 Present；不从源码推导性能等价。 |
| [tests/scene/test_window.cpp](../../../../../tests/scene/test_window.cpp)、[DisplayServerMock](../../../../../tests/display_server_mock.h) | 已有 Window 单元测试依赖 mock；不能证明真实 HWND 不闪窗或 GPU 提交成功，须增加 Windows 集成测试。 |
| [modules/mono/README.md](../../../../../modules/mono/README.md) | 本仓库 .NET 构建流程；仅 MCP 验收依赖此构建。 |

## 2. Overall approach

采用进程级、启动后只读的 offline 状态，不增加 DisplayServer 类型，也不把 Win32 类型传入渲染抽象层。

```text
Main 解析引擎参数（用户参数分隔符之前）
  -> 校验显式冲突与平台
  -> OS Windows offline 初始化 / HighQoS
  -> 项目配置与渲染选择，验证隐式冲突
  -> DisplayServerWindows 正常初始化
       -> 创建隐藏 HWND / 图形设备 / 交换链
       -> 窗口显示、样式、焦点路径统一受限
  -> 原有 SceneTree / 编辑器 / 消息泵 / RenderingServer / Present
  -> 渲染、窗口、工作线程清理
  -> 释放本次执行速度覆盖
```

主渲染路径不判断截图工具类型，不增加对 Godot-MCP 的依赖。MCP 在隔离测试项目中使用现有 Viewport/SubViewport API。

## 3. APIs and data model

以下均为拟新增的内部 C++ API，不是现有 API，也不新增脚本绑定：

- `OS::is_offline_mode() const -> bool`：读取只读进程状态，默认 false。
- `OS::initialize_offline_mode() -> Error`：受保护平台虚函数，由 Main 在启动阶段调用；默认返回 `ERR_UNAVAILABLE`。Windows 实现只允许在 DisplayServer 创建前成功启用。
- OS 持有受保护的模式状态，Windows 成功申请 HighQoS 后才设为 true；未启用时不调用额外的电源 API。错误直接记录，不用 `OS.alert()` 报告申请失败。
- Windows 私有 HighQoS guard 提供一次申请和幂等释放，记录本实例是否成功持有覆盖。使用进程伪句柄，不关闭 `GetCurrentProcess()` 的返回值。结构 Version 为当前版本，ControlMask 仅为 EXECUTION_SPEED，StateMask 为 0。
- guard 由 OS_Windows 生命周期持有，跨 DisplayServer 构造失败/回退仍有效，不在渲染初始化失败时过早释放。清理将执行速度控制交回系统（ControlMask/StateMask 均为 0）；这不是恢复任意外部调用者先前自定义的策略，首版不支持嵌入 libgodot 宿主的此参数生命周期。
- Windows API 不可用或失败统一 `ERR_UNAVAILABLE` / 非零启动退出，并输出 Win32 错误码。旧系统不应因新增静态导入破坏普通模式，按本项目兼容约束使用动态解析或等价兼容封装。
- 状态在工作线程与渲染初始化前发布，运行时不提供开关；读取无需新增跨线程同步。资源和回调保持原有窗口线程/渲染线程规则。
- 模式仅属于此次进程，不写入 project.godot、EditorSettings 或布局文件。普通退出仍执行既有的布局保存；不得把隐藏误判为最小化或零尺寸而污染布局。

## 4. Algorithms and rules

### 4.1 启动解析

1. 在现有主解析器识别 `--offline`，重复出现幂等。不在 Windows 入口再解析一遍 argv。
2. 记录显式 headless、display/rendering 选择及 `--wid` 的出现，完成顺序无关的冲突检查；不要只检查可能已被后续参数覆盖的最终字符串。
3. 在参数区结束后、项目资源加载和首个图形探测/初始化前申请 HighQoS。`--help` / `--version` 仍沿用现有无图形早退，不额外申请策略。
4. 项目配置、dedicated_server 特性、渲染方法和编辑器布局确定后再验证有效配置，最迟在 DisplayServer 构造前拒绝隐式 headless/dummy、独占全屏。配置失败也走正常 guard 清理。
5. 将参数加入 TOOL/PROJECT 转发列表时必须排除 `--` / `++` 后的用户参数。保留 Godot 其他未知/重复参数的现有处理。

### 4.2 原生显示门控

- 封装 Windows 私有的显示/激活操作，审计所有 `ShowWindow`、`WS_VISIBLE`、`SWP_SHOWWINDOW`、`SetForegroundWindow`、`SetFocus` 路径；不能仅在 Main 跳过 `show_window()`。
- `_get_window_style()` 的最终结果在 offline 下去掉可见位，创建和更新均使用相同规则。所有本变更管理的 `SetWindowPos` 操作避免激活；模式切换、无边框和换屏不能重新显示。
- `show_window()` 保留初始化、窗口关系和正常记账，只门控原生显示/激活副作用。`_create_window()`、后端回退重建和 subwindow 创建自始遵守策略。
- 离线窗口需要用明确的请求模式和客户区几何维护状态：窗口化保留保存的普通矩形；最大化使用屏幕工作区；普通全屏使用屏幕矩形和现有边界补偿。用无激活的尺寸/位置 API 更新隐藏 HWND，不调用 ShowWindow 来取得布局。
- 如需补充 WindowData 的离线请求模式/恢复矩形，状态归每个窗口所有。离线分支的 `WM_WINDOWPOSCHANGED` 不能用隐藏 HWND 的 `IsZoomed`/`IsIconic` 覆盖逻辑请求模式，但仍需同步实际客户区、DPI 和渲染 surface 尺寸。普通分支保持原算法。
- 显式最小化保留逻辑 minimized 和原有不绘制语义，不因 offline 自动进入该状态；恢复后必须得到有效尺寸并继续隐藏绘制。独占全屏启动/创建失败，运行期设置被拒绝且不改变先前状态。
- 不修改 Window/Viewport 的逻辑可见性来实现隐藏，不强制所有 Viewport UPDATE_ALWAYS，不令 can_draw 无条件返回 true。
- 禁止 offline 路径的原生前台切换、焦点恢复、鼠标捕获/裁剪/warp 等桌面副作用；保留内部输入模式记账，不伪造前台焦点事件。应用依赖真实焦点的暂停逻辑保持原样。

### 4.3 原生交互和错误

- `OS_Windows::alert()` 在 offline 下记录文本并返回，保留调用者原有退出决定。
- `_create_window()` 中直接 MessageBox 的错误分支及 DisplayServer 创建失败提示同样改为非交互报告，确保初始化失败返回 Main 并非零退出。
- 原生文件对话框的统一实现入口在创建线程/COM 对话框前排队一次取消回调，保持普通/带 options 两种既有签名并返回 OK；空结果不代表成功选中文件。
- `dialog_show()` / `dialog_input_text()` 在 offline 下返回 ERR_UNAVAILABLE，不创建窗口，不调用选择结果回调。不盲目关闭或确认 Godot 自绘模态窗口。
- 进程托盘/原生菜单等额外 UI 入口在实施审计中禁止产生可见交互或返回不支持，不声称能拦截扩展直接调用的 Win32 API。

### 4.4 编辑器进程传播

- Main 现有 TOOL/PROJECT scope 承载参数；检查 EditorRun、Project Manager 和 EditorNode 重启均使用该机制。
- GameView 在 offline 下把运行期嵌入可用性设为不可用，覆盖参数注入、开始嵌入及焦点恢复调用点。不能只跳过 `--wid` 注入但留下父进程 `embed_process()`。
- 不永久改写 embed-on-play 配置。作为兜底，DisplayServerWindows 的进程嵌入显示入口在 offline 下拒绝嵌入，不创建可见临时焦点窗口。正常模式不变。
- 子进程各自验证参数和申请 HighQoS；不依赖父进程电源策略是否继承。首版不承诺编辑器自动把子进程失败映射为父进程退出失败。

### 4.5 渲染与截图

保留 Main::iteration、RendererViewport、交换链创建和 Present 的既有职责。默认不修改 Vulkan clipped、D3D12 present flags、VSync 或帧率策略。若实测发现隐藏 HWND 下提交停滞，必须定位后端原因并记录，不以取消 Present 或增加替代目标绕过本契约。

编辑器按需更新仍有效。MCP 请求需要图像时应由原有场景更新/截图流程推动帧绘制；这与要求编辑器空闲时无限重绘不同。相机/隔离工具原有 SubViewport 是合法的插件行为，但不能充当主交换链正常工作的证据。

## 5. Fixed decisions and discretion

固定：Windows 进程策略、真实图形路径、HighQoS 失败早退、原生全程隐藏、逻辑可见性与原生可见性分离、非嵌入子进程、原生交互失败/取消语义、MCP 三项实际验收。首版范围及限制以规格为准，不扩大为真正 headless 或 benchmark 模式。

可由实施者选择：Windows helper/guard 的私有类型名与文件拆分、符合仓库风格的错误文本、集成夹具和脚本位置、失败注入的仅测试接口。不可为了测试方便添加生产环境隐藏开关或改写公共渲染算法。

没有待定的核心行为决策。环境前提尚未验证：可用图形后端、.NET 构建依赖、选定 MCP 版本与 4.8-dev 兼容性、实际工具 schema 和连接方式。实施阶段先固定并验证环境；任一必测路径受阻则保留任务未完成，不将环境缺失当作通过。

## 6. Verification and documentation impact

执行任务见 [tasks.md](tasks.md)。窗口/CLI/错误覆盖 [S1–S6](specs/offline-window-mode.md#acceptance-scenarios)，MCP 覆盖 [M1–M5](specs/mcp-screenshot-compatibility.md#acceptance-scenarios)。

- 单元测试覆盖参数状态、样式/模式策略和失败注入；真实 Windows 集成测试负责 WinEvent/EnumWindows、桌面焦点、客户端尺寸和实际 GPU 路径，不能依赖 DisplayServerMock 得出结论。
- 对所有本机可用真实图形后端运行启动/渲染测试，记录实际回退。至少一个后端完成所有 MCP 测试；对不可用组合明确报告。
- 使用同一构建、同一夹具进行可见/隐藏对照。窗口事件监控早于进程创建，周期枚举补充长期状态检测，单张桌面截图不能证明从未闪窗。
- 构建普通编辑器/模板与包含 `module_mono_enabled=yes` 的编辑器；.NET glue 和程序集按本仓库 [Mono 构建说明](../../../../../modules/mono/README.md)生成，实际二进制名称以产物为准。
- MCP 安装在独立测试项目中，输出到临时测试产物目录或 CI artifacts；不要将下载的插件、NuGet 缓存或 PNG 加入引擎源目录。核对 schema 后真实调用并查看图像，保存请求参数、图像断言和窗口监控证据。
- 测试代码/夹具是可重复的验证入口；PNG、日志和临时测试项目是运行产物。创建阶段不安装插件、不启动服务、不运行这些测试。
- 实现交付后更新[当前架构](../../../../architecture.md)，在当前规格目录新增 doco/specs/windows-offline-mode.md。当前没有需要取代的 ADR，不为简单实现细节另建决策文档。

外部依据：[Windows SetProcessInformation](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-setprocessinformation)、[QoS 定义](https://learn.microsoft.com/en-us/windows/win32/procthread/quality-of-service)、[Vulkan 交换链 clipped 语义](https://github.khronos.org/Vulkan-Site/refpages/latest/refpages/source/VkSwapchainCreateInfoKHR.html)、[Godot-MCP README](https://github.com/IvanMurzak/Godot-MCP)。外部项目的实现是参考，不是本引擎已经满足的契约。
