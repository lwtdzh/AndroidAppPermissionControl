# Android 截图检测调查与防护记录

调查开始日期：2026-11-06。初始记录针对 ScreenshotShield 0.1.2；当前模块为 0.1.4，独立检测软件为 0.1.1，更新验证见文末补充。调查对象是被 Vector 注入的应用进程；文件识别使用名称、路径和元数据，不扫描相册图片的像素或做内容分析。

## 截图信息可以从哪些地方取得

Android 14 引入 `Activity.ScreenCaptureCallback`。应用在可见 Activity 上注册后，系统可以通知截图事件；回调本身不提供截图图片。官方文档也明确指出 ADB `screencap` 和测试框架抓图不属于这条检测链路。该接口的存在和调用方式有官方文档及 AOSP 实现证明。<a href="#source-1">[cite:1]</a><a href="#source-2">[cite:2]</a>

旧版本和一些 SDK 使用 `ContentObserver` 监听 MediaStore，再查询文件名、目录和添加时间。即使不读取图片内容，最近时间、截图目录和文件名也足以实现常见检测。BugScreen 的公开实现同时展示了官方回调、相册监听，以及仅查找最新截图的 Bundle 查询。这是一个具体 SDK 的实现证据，不代表所有国产 App 都采用相同代码。<a href="#source-3">[cite:3]</a>

通知监听和无障碍服务是另外两类信息入口。获得用户授权的通知监听服务可以收到通知新增、移除及排名变化；无障碍服务可以收到 UI 事件并读取节点和窗口。若系统截图产生了带截图标识的通知、浮层或节点，这些元数据可以成为识别依据。官方文档和 AOSP 源码证明了这些读取能力；本次没有证据证明某个指定国产 App 已经用它们检测截图。<a href="#source-4">[cite:4]</a><a href="#source-5">[cite:5]</a>

剪贴板可以承载 URI 和图片类型的描述信息。若截图操作同时复制图片或 URI，应用可以从 `ClipData`、`ClipDescription` 和变化通知获取线索。截图是否自动进入剪贴板取决于 ROM 和具体操作，不能推广为所有手机的固定行为。<a href="#source-6">[cite:6]</a>

文件系统访问和广播也需要检查。应用可以直接查询文件、列出目录或使用 inotify 接收变化；厂商还可能发送截图相关广播。AOSP 分别通过 `LoadedApk.ReceiverDispatcher.Args` 和 `ActivityThread.handleReceiver` 向动态、静态接收器交付广播。广播机制有源码证明，任意厂商的私有 action 名称仍需要实际证据。<a href="#source-7">[cite:7]</a>

## 0.1.2 的处理方式

全部拦截默认开启，应用范围由 Vector 管理。模块不显示桌面入口；`MAIN + MODULE_SETTINGS` 和 `MAIN + INFO` 保留框架内的说明页入口，兼容 Vector 2.2 的设置解析方式。独立日志 App 保留桌面入口。<a href="#source-8">[cite:8]</a>

| 信息入口 | 当前处理 | 具体适用条件 |
| --- | --- | --- |
| 官方截图回调 | 拦截 Activity、ScreenCaptureCallbackHandler 和 ActivityTaskManager 代理 | 运行时存在相关方法 |
| 直接 `BinderProxy.transact` 注册 | 读取当前系统生成的 transaction 字段，核对接口名，返回合法的 void AIDL reply | 接口为 `android.app.IActivityTaskManager`，事务对应注册或注销截图 observer |
| MediaStore 查询 | 执行前添加截图排除条件，覆盖旧式 selection、Bundle、client 和 provider proxy | 图片/文件表，不向旧式 thumbnails 表添加不兼容的文件名 SQL |
| `_id`、时间或数量查询 | 相同的 SQL 过滤先在 provider 执行 | 不依赖调用者投影中包含文件名；过滤后才执行原查询的排序、limit 或聚合 |
| MediaDocuments 与旧式 thumbnails | 使用 document ID/image ID 查回 MediaStore；需要时增加识别列，过滤后隐藏额外列 | 系统文档或缩略图 schema。不是对任意第三方 provider 猜测列名 |
| 其他内容 URI | 查询结果按现有名称/路径列过滤；打开时识别 URI 和可取得的元数据 | provider 正常提供元数据且当前应用有访问权限 |
| 相册变化通知 | 过滤截图 item，混合数组保留普通 item；集合/null 通知在媒体 observer 上抑制 | 无 item 身份时不能精确区分普通图片变化，因此刷新可能延迟 |
| Java 文件读取 | 隐藏元数据、列表及输入流 | 共享存储中带截图标识的路径 |
| native 文件读取 | 拦截 open/openat、stdio、stat 家族、目录枚举、readlink/realpath 等；解析符号链接和 proc 别名 | libc 实际可 hook 的入口，以及经过 libc syscall trampoline 的已实现调用 |
| 已打开的文件描述符 | 在 read/readv、pread/preadv、fstat、mmap 等入口重新识别 fd 目标 | fd 在 `/proc/self/fd` 中仍指向可识别的截图文件 |
| 文件监听 | 直接截图目录拒绝监听；普通父目录事件按名称过滤；dup/fcntl 别名共享 watch 状态 | 事件仍经过已 hook 的读取入口 |
| 动态、静态广播 | 交付前完成 PendingResult 并抑制回调 | action 最后一段包含截图标识 |
| 剪贴板 | 隐藏图片截图描述、可识别 URI 及描述可识别的变化事件 | 不为判断 `hasPrimaryClip` 或派发 listener 额外读取图片内容；普通文字保留 |
| 通知 | 动态 hook 具体服务回调；过滤 active/snoozed 列表和已识别排名 key | Android/SystemUI 或可识别截图组件的标题、正文、channel 等元数据符合截图规则 |
| 无障碍 | 动态 hook 具体服务回调；过滤可识别截图事件、窗口、根节点、焦点和 InteractionClient 查询结果 | 系统/截图组件的类名末段、view ID 末段或文本符合规则；节点扫描有数量上限 |

通知层保留框架的 ranking 更新，再拦截应用回调，避免直接跳过 wrapper 导致其他通知的排名状态丢失。已识别的截图通知 key 在本进程内继续隐藏，防止移除时的精简通知缺少完整正文。无障碍类名和资源名使用末段判断，避免因为普通应用的包名包含 `screenshot` 而屏蔽它的正常 UI。<a href="#source-4">[cite:4]</a>

识别标识包括 `Screenshot`、`Screen_shot`、`Screen-shot`、`Screen shot`、`Screencap`、`Screen_capture`、截图、截屏、螢幕截圖和屏幕快照。遇到只有数字、无可识别目录或使用其他厂商命名的记录，不能仅凭当前规则证明它是截图。

## 验证方法与证据性质

运行环境为专用 Android 16 ARM64 模拟器，使用 Magisk/Zygisk 和 Vector 2.2。比较模块关闭、开启且在作用域内、开启但在作用域外的行为，并保留普通图片、文件、广播和文本作为对照。通知与无障碍回调使用构造元数据检查拦截入口；它们不等于真实 ROM 截图产物。

系统截图验证注入 SYSRQ 快捷键，由 Android 输入策略和 SystemUI 实际保存截图。分别检查普通官方 API 和手写 Binder observer 的回调。发现当前系统的 AIDL transaction 字段时，测试暂时放宽隐藏 API 反射策略；保护状态以及独立官方截图对照使用恢复后的默认策略。测试没有改变模块所需权限。

ARM64 测试夹具用内联系统调用打开已存在的文件，以获得一个绕过 libc open hook 的 fd，模拟从未注入进程收到的 fd。再检查 libc read/pread/readv/preadv、fstat、mmap、fcntl 副本及 proc 路径访问。此夹具同时证明：内联 `svc` 本身能够绕过 libc hook，不能将后续读取拦截描述成所有内联系统调用均受到保护。

文档提供者测试需要通过系统 `ACTION_OPEN_DOCUMENT` 选择夹具并取得实际 URI 授权。仅用 shell 给 Intent 加授权 flag 不足以取得 MediaDocuments 权限；系统拒绝访问的结果不能作为模块过滤成功的证据。

### 已通过的前后对照

| 验证项目 | 模块关闭 | 开启且在作用域内 | 开启但在作用域外 |
| --- | --- | --- | --- |
| Java/NIO、libc 和已实现 syscall 的截图文件访问 | 可见 | 隐藏 | 可见 |
| 普通文件访问 | 可见 | 可见 | 可见 |
| 已打开 fd 的 read/pread/readv/preadv/fstat/mmap、fcntl 副本 | 可读 | 截图不可读，普通文件可读 | 可读 |
| 符号链接、proc fd/root、readlink 和 statx | 截图可见 | 截图隐藏，普通文件保留 | 截图可见 |
| MediaStore legacy/Bundle/client 和 `_id` 投影 | 2 行 | 1 行普通图片 | 2 行 |
| SAF 截图文档，只请求 `document_id` | 1 行、1 列，可打开 | 0 行、1 列，不可打开 | 1 行、1 列，可打开 |
| SAF 普通图片文档 | 1 行、1 列，可打开 | 1 行、1 列，可打开 | 1 行、1 列，可打开 |
| 动态、静态截图广播及文件监听事件 | 到达 | 截图抑制，普通事件到达 | 到达 |
| 构造的截图通知/无障碍回调 | 到达 | 截图抑制，普通回调到达 | 到达 |
| 图片截图剪贴板描述、内容和 has 查询 | 可见 | 隐藏，普通文字可见 | 可见 |

独立官方截图对照使用 SystemUI 保存的新截图：关闭模块时，标准 API 和直接 Binder observer 各收到 1 次回调；开启时，两者都为 0，系统仍保存了截图。此对照不把 ADB 文件夹具或手工调用 listener 算作真实官方截图事件。

独立“截图检测日志”App 也完成了四次真实截图对照：官方回调、相册监听在保护前分别显示 1 条日志，保护后均为 0 条；四次操作均由 SystemUI 保存了新截图。具体记录见 `../module-screenshot-detector/verification/detector.json`。测试结束后，日志 App 的临时语言和作用域已恢复，隐藏 API 测试策略也恢复为未设置。

桌面 `MAIN/LAUNCHER` 查询返回零个 Activity；框架 `MODULE_SETTINGS` 查询返回说明页，该入口实际启动成功。八份语言资源文件的 key 集合一致。四种 native 架构编译及 release lint 通过，lint 仍有目标 SDK、无图标及兼容属性等警告。

旧式 thumbnails、第三方内容 provider、剪贴板 listener、通知 active/snoozed/ranking 的每个读取变体，以及无障碍窗口/节点的每个读取变体没有逐项完成运行验证。它们有已实现的 hook 和来源依据，不能计入上述已通过的实际运行对照。完整运行记录随源码保存在 `verification/`。

## 尚不能保证的情况

以下项目是具体的实现限制，不能用“拦截全部开启”来解释为已覆盖：

- **内联系统调用和未注入的程序**：App 的 JNI 代码可以自己执行 `svc`；exec 出来的外部工具和独立辅助服务也可能不加载模块。当前测试已经直接展示前一种情况。
- **其他原始 Binder 协议**：标准 Java provider proxy 受到拦截，任意手写的 ContentProvider Parcel 和厂商私有 Binder 协议没有全部解析。媒体查询元数据仍可能从这种路径取得。
- **文件失去截图标识**：重命名并移到普通目录后，路径规则可能无法识别。匿名管道、已经复制到私有存储的副本和此前缓存的数据同样可能没有原路径。
- **不同 ROM 的通知、广播和 UI 名称**：没有已识别标识的数字 action、channel 或节点不能可靠分类。需要结合实际样本补规则；不会仅凭猜测批量屏蔽整个 SystemUI。
- **时间和资源变化推测**：目录修改时间、存储使用量、窗口焦点变化、提示音、震动，以及 inotify fd 的 poll/epoll 就绪状态仍可能成为旁路线索。即使读取时把事件过滤掉，内核已经让 fd 变为可读，也可能暴露“发生了某种变化”。
- **通知排名和窗口的间接变化**：隐藏明确的截图条目不等于消除所有列表变化、rank 数字变化或窗口消失的推测。
- **系统/root 权限及额外采集能力**：高权限服务、已授权的持续屏幕采集或其他独立进程，可能观察到当前应用进程以外的信息。
- **图片内容分析**：遍历图片或读取最近图片进行内容识别不在防护范围内；模块没有实现像素扫描、OCR 或模型识别。

因此，可以证明的是已实现入口在已测环境中的具体效果。对于未知 App、未知厂商协议和任意旁路，当前实现无法证明百分之百防御。

## 使用影响

作用域内应用看不到被识别的截图，因此选图、上传截图和粘贴截图也可能受影响。只写文件访问保留，读写模式可能受到拦截。集合通知抑制可能延迟普通图片刷新；通知和无障碍过滤可能影响目标应用针对截图 UI 的功能。全局系统截图保存不受这些应用进程 hook 改写。

安装包包含 ARM64、ARM32、x86_64、x86 库；编译通过与 ARM64 模拟器测试不能代替其他架构及 ROM 的运行验证。用户反馈的 vivo 测试通过属于此前版本和此前操作的证据，不能直接推广为 0.1.2 新增路径全部真机通过。

## 0.1.3 与独立检测软件的补充

检测软件 0.1.1 已加入 18 个自动入口与通过真实选图授权执行的读取检查。它使用独立的 MediaStore observer / Bundle / legacy / client 查询、Java 文件监听与元数据、native inotify / libc / syscall、剪贴板、广播、通知和无障碍服务，分别显示权限、连接及可用状态。已有图片、通知和窗口先作基线；日志计数表示各入口的信号条数。

实际 SystemUI 截图在模块作用域外触发 13 个入口，加入作用域后全部为零，系统仍保存截图。直接 Binder 通过读当前 framework 的生成常量完成注册，全程使用默认隐藏 API 策略；此检测软件不需要像旧 Probe 的反射夹具一样暂时更改全局策略。

新增检测软件还发现：0.1.2 的动态广播在真实框架交付中仍能调用接收器，旧的 Args 入口验证没有覆盖这一实际交付结果。0.1.3 补充在注册时动态 hook 接收器具体 `onReceive`，保留框架的 PendingResult 完成流程；实际动态、静态广播夹具的保护前后对照已通过。框架源码中的 Args 入口继续保留作为另一层拦截；尚未把这个漏拦截的具体 ART 优化原因作为已证明结论。

本次 ROM 截图没有生成可识别的新通知或截图剪贴板，故未将这两个入口的零信号算成真实截图验证。完整说明见 `../module-screenshot-detector/README.md`，新增记录见 `../module-screenshot-detector/verification/detector-expanded.json`。0.1.2 的既有记录保留历史版本标注。

2026-11-08 在 vivo V2419A、Android 16 真机安装 0.1.3 / 0.1.1。系统实际投递的测试通知在保护前触发通知回调 2 条、列表 2 条，图片剪贴板触发 1 条；加入模块作用域并重启后均为 0，系统里的测试内容仍存在。普通截图没有自动产生这两类新信号，故真机通知/剪贴板对照明确使用测试内容。原剪贴板、作用域和通知授权已恢复，原有通知监听与无障碍设置未被改动，详情见 `../module-screenshot-detector/verification/vivo-notification-clipboard.json`。

## 0.1.4 native 兼容性修复

2026-11-08，在 Android 16 ARM64 专用模拟器与 Vector 2.2 上，什么值得买官方版 11.2.3 已通过三次作用域内冷启动，每次观察 60 秒。另一次冷启动观察 60 秒并发送上、下滑手势，主进程与前台保持正常；每次均启用 34 个 native hook。

Vector 的符号缓存保留了一份完整的 linker 磁盘文件映射，OAID SDK 会误把这份文件视图当成运行中的加载器。模块初始化现在将符合完整文件长度、只读共享权限和 ELF 条件的副本原位替换为匿名只读映射；`mremap` 保留缓存使用的地址和内容，真正运行的 linker 映射保持原样。

原 C++ `syscall` 包装也存在换栈问题：新增的原始 `clone` 测试中，旧版子进程不能正常退出。0.1.4 通过四种 ABI 的汇编入口，只让已实现的文件访问和 fd 跟踪调用进入原过滤函数；其他调用直接跳回 libc，保留原栈和返回地址。换栈、`getpid` 与六参数非零偏移 `mmap` 在模块关闭、作用域内、作用域外三种状态下均通过。这证明了已复现的换栈缺陷得到修复；本次没有把应用内部全部 `syscall` 使用情况作为已逐条确认的事实。

完整拦截对照通过：Java/NIO、libc、已实现 syscall、既有 fd、inotify、MediaStore、真实 SAF URI 授权、广播、剪贴板及构造回调测试保留原效果，普通文件和图片可用。真实 SystemUI 截图仍保存；官方 API 与直接 Binder 的基线回调各 1 次，保护后均为 0。独立检测软件真实截图的 13 类入口从有信号变为全部零；真实选图授权后的可用读取入口隐藏截图、保留普通图片。`/proc` 重开 fd 的一个入口在基线已经失败，未计作拦截证据。

本次测试没有使用 ptrace 或进程内存补丁。完成后恢复原作用域、服务设置、隐藏 API 策略与语言设置，并删除新增测试截图。实际运行验证只涉及 Android 16 ARM64 模拟器；其他三种 ABI 已编译，不作为实测。匿名副本会使用私有页，本模拟器 linker 文件约 2.15 MiB。

记录：[发布汇总](verification/release-0.1.4.json)、[拦截与普通操作](verification/integration-0.1.4.json)、[真实系统回调](verification/official-callback-0.1.4.json)、[冷启动](../module-screenshot-probe/verification/smzdm-cold-starts-0.1.4.json)、[手势操作](../module-screenshot-probe/verification/smzdm-scroll-0.1.4.json)、[检测软件截图信号](../module-screenshot-detector/verification/detector-expanded-0.1.4.json)、[真实选图读取](../module-screenshot-detector/verification/detector-read-0.1.4.json)。

## 资料来源

<a id="source-1"></a>[cite:1] Android Developers：Detect when users take device screenshots<br>
https://developer.android.com/about/versions/14/features/screenshot-detection

<a id="source-2"></a>[cite:2] AOSP Android 16：ScreenCaptureCallbackHandler / IActivityTaskManager<br>
https://android.googlesource.com/platform/frameworks/base/+/refs/heads/android16-release/core/java/android/app/ScreenCaptureCallbackHandler.java<br>
https://android.googlesource.com/platform/frameworks/base/+/refs/heads/android16-release/core/java/android/app/IActivityTaskManager.aidl

<a id="source-3"></a>[cite:3] BugScreen：How screenshot detection works on Android，2026-07-02，公开 SDK 实现说明<br>
https://www.bugscreen.app/blog/how-screenshot-detection-works-on-android

<a id="source-4"></a>[cite:4] AOSP Android 16：NotificationListenerService<br>
https://android.googlesource.com/platform/frameworks/base/+/refs/heads/android16-release/core/java/android/service/notification/NotificationListenerService.java

<a id="source-5"></a>[cite:5] Android Developers：Create an accessibility service<br>
https://developer.android.com/guide/topics/ui/accessibility/service

<a id="source-6"></a>[cite:6] Android Developers：Copy and paste<br>
https://developer.android.com/develop/ui/views/touch-and-input/copy-paste

<a id="source-7"></a>[cite:7] AOSP Android 16：LoadedApk / ActivityThread 广播交付<br>
https://android.googlesource.com/platform/frameworks/base/+/refs/heads/android16-release/core/java/android/app/LoadedApk.java<br>
https://android.googlesource.com/platform/frameworks/base/+/refs/heads/android16-release/core/java/android/app/ActivityThread.java

<a id="source-8"></a>[cite:8] Vector 2.2：DaemonClient 的模块设置入口解析<br>
https://github.com/JingMatrix/Vector/blob/v2.2/manager/src/main/kotlin/org/matrix/vector/manager/ipc/DaemonClient.kt
