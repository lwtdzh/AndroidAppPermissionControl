# 应用状态屏蔽 · 整合设计

本次整合名称为“应用状态屏蔽”，英文名 AppStateShield，当前版本 0.3.1。目标是让 Vector 作用域内的应用读不到指定系统状态，同时保留用户实际使用的系统功能。

## 项目与应用

根目录成为一个 Gradle 工程，只保留一个 wrapper。`:app` 构建整合模块，`:verifier` 构建保留的验证应用。旧的按能力拆分的独立工程移除；历史验证记录归入 `verification/legacy/`。脚本统一在 `scripts/`，人工测试手册在 `docs/TEST-MANUAL.md`。

主模块包名为 `io.github.lwtdzh.appstateshield`，保留 Vector 的 MODULE_SETTINGS/INFO 入口。0.3.1 增加默认 disabled 的 Launcher activity-alias，目标仍为 SettingsActivity；首页图标开关通过 PackageManager 设置当前 Android 用户的组件状态，不写入屏蔽策略，也不改变 Vector 作用域。开启后可供桌面和分身工具发现；工具的分身支持需另行确认。验证应用保留 `io.github.lwtdzh.screenshotdetector` 的包名和签名身份；原来的截图监听、截图低层 Probe 和设备状态 Probe 都进入同一个 APK。

验证工程的 debug flavors 生成 A/B 测试目标，使用同一份源代码和独立 package/UID，供多应用配置检查使用。正式交付只需要整合模块与主验证 APK。

验证器的 VPN 夹具只路由 TEST-NET。停止命令直接关闭 TUN 并移除前台通知，再调用 stopSelf；系统 VPN 绑定可能延迟 onDestroy，不能只在销毁回调里关闭接口。普通主进程检查不会停止独立的 :vpn 夹具进程。

## 方法与默认配置

整合提供截图状态、VPN 状态、网络代理、开发者选项、USB/无线调试、SELinux 六种独立方法。调试方法包含原有的 USB 和无线调试设置及原生属性。SELinux 的稳定 ID 为 selinux，旧定制升级后默认开启。

每个定制条目只保存应用包名与“已关闭方法 ID”的集合，空集合表示全部开启。未定制应用也使用空集合。新增方法的 ID 不会自动出现在旧的关闭集合里，因此上线后默认开启。删除定制条目恢复全部开启；“关闭已实现方法”只关闭当前已实现的 ID。

Vector 统一控制注入范围。定制列表不改变 Vector 的作用域。配置在目标应用启动时读取，保存后需要强行停止并重新打开目标应用；旧进程使用启动时取得的配置。

## 配置传递与隔离

模块设置保存在私有 SharedPreferences 中，更新必须使用同步原子提交。只读 ContentProvider 向调用方提供其自己的配置；调用方 UID 必须拥有请求的包名。写入仅由模块自身 UI 完成，其他应用无法改配置，也无法读取另一应用的配置。

模块入口在 `Application.attach(Context)` 原方法执行前取得配置，并安装被选中的 Java/native Hook，确保目标应用的 `attachBaseContext`、ContentProvider 和 `onCreate` 使用同一份配置。主模块自身不注入，避免配置服务递归。正常同包多进程共用配置。

整合保留原有三个 native 库，并新增 selinuxstate，均只在对应方法启用时加载。截图 syscall 汇编分派、原生列表成对释放和 Vector 链接器映射兼容处理保持不变。VPN 与网络代理拆开；开发者选项与调试状态拆开。关闭调试方法时，Java/native 调试属性都保持原值。

SELinux 在同一 Application.attach 前安装。Java 的 android.os.SELinux.isSELinuxEnabled/isSELinuxEnforced 返回 true；native 的 security_getenforce/is_selinux_enabled 返回 1。已存在的 ro.boot.selinux 文本返回 enforcing，缺失的属性和调用方默认值保持原样；这个启动属性不能替代真实运行时模式。新库通过 RTLD_DEFAULT 和 Vector 的库加载回调取得符号；系统私有 libselinux 已由 zygote 加载但应用 namespace 不允许 dlopen 时，从该库实际加载的 ELF 动态符号表定位已定义函数。共用解析代码在 shared/native/loaded-symbol.h，不加载或复制系统库。

native read、__read_chk、pread/pread64、readv、fread、fgets 先使用真实 FD 读取，只对 /sys/fs/selinux/enforce 或 /selinux/enforce 的实际返回字节将 0 改为 1。通过 /proc/self/fd 识别目的文件，不缓存 FD 编号；dup、关闭后复用、相对路径和符号链接沿用真实文件语义。失败、EOF、偏移和 errno 保留；普通同名文件不改。fread 使用真实字节数处理不完整的末项，不把它误算成完整项。系统模式、安全上下文、写入权限都不修改。

Vector 不允许重复 Hook 同一个函数。截图库与开发者库提供两个内部过滤器注册入口，仅接受各自已安装的原生符号；SELinux 使用这些入口追加读取/属性过滤。截图关闭或调试关闭时，相应入口不存在或未安装，SELinux 自己安装该组 Hook。注册使用原子函数指针，不改截图 syscall 汇编、clone 分派或原有内存释放逻辑。

SELinux 的 native 入口使用与 0.2.1 相同的两类 ARM64 跳转识别，保留加固库的外部跳转。直接 syscall / 内联汇编、未注入子进程、其他挂载路径、未 Hook 的读取函数以及保留入口不属于已验证的保护路径。

模块 0.2.1 在 ARM64 安装截图 native Hook 前检查现有入口。对于已跳到其他库或匿名代码的 `B`，以及 `LDR Xn, [PC+8]; BR Xn; .quad target`，保留应用已有跳转；跳转仍位于同一库的普通包装函数继续处理。跳过的符号名写入日志，供兼容检查使用。此处理不使用应用包名名单，不改变配置或安装时机，也不改 syscall 汇编。只识别这两种 ARM64 入口；其他跳转形式及其他 ABI 的加固兼容尚未验证。保留入口的原生读取没有完整保护，不能以应用正常启动或 Hook 数量代替截图屏蔽证据。

验证应用提供“是否注入/实际安装的方法”标记，与“存储的配置”分开显示。标记不是实际状态屏蔽的替代证据，仍需真实系统状态和普通操作对照。

截图日志页在 ContentObserver 注册、FileObserver startWatching 完成后才显示相应来源就绪。FileObserver 监听 CREATE、CLOSE_WRITE 和 MOVED_TO，覆盖不同截图保存方式。Java FileObserver 共享 inotify 线程；新日志页开始监听前，先停止上一日志页，避免旧页延迟 onStop 删除新页对相同目录的 watch。页面停止时只清除自己持有的 Signals.listener。

截图方法在注册 MediaStore observer 时保存可见普通行的元数据快照。系统通知没有图片 ID 时，只有普通行实际新增、删除或修改才放行；仅截图变化不会改变该快照。快照查询失败或无权限时仍抑制不明通知。普通行很多时，集合通知会增加一次元数据查询的成本；没有扫描图片内容。嵌套 dispatchChange 只在最外层判断，避免同一次通知被重复比较后误拦截。

## 设置交互

验证器首页的 ObservedState 只读取 ConnectivityManager、Settings.Global 和 SELinux API/enforce 文件，每 2 秒在后台线程刷新，页面退出前台后停止轮询。它不调用包含代理请求、文件写入等测试夹具的完整 Probe。异常单独显示无法读取，模块注入提示与状态值同时可见。SELinux 优先使用 enforce 文件的实际 0/1；文件不可读时，Java API 的 false 可能来自 security_getenforce 失败，显示“模式无法确认”，不能据此断言 Permissive。

ScreenshotSession 与传统来源信号计数分开。相同文件路径和相同 MediaStore ID去重；不同入口的信号在 2 秒窗口内合并，重复官方回调、同一入口的不同图片仍增加次数。无身份的重复浮层信号在窗口内合并，因此截图次数标为估算。最近身份最多保留 1024 个，超过后淘汰最旧项。保存状态时序列化会话以保留旋转/进程重建期间的次数和去重信息；后台不新增信号，清空日志或重启监听不重置会话，新页面/冷启动使用新会话。

模块页显示默认策略、定制列表与“添加应用”。应用选择支持按名称/包名搜索和系统应用筛选。应用详情显示每种方法的用途、开关和保存按钮；添加应用时默认全部开启。

保存、取消、返回、未保存修改提示、恢复默认、重复选择、卸载后的条目、旋转/进程重建、列表排序和语言切换都需要人工手册覆盖。取消不得产生配置；恢复默认不得影响其他应用。SELinux 显示独立开关及“向应用返回强制执行状态，保留系统实际模式”说明。

## 验证要求

先建立无保护的真实 VPN、开发者/USB、SELinux、系统截图基线，再执行默认、定制空集合、单方法、全部关闭、逐项更改、两个应用相反配置和第三个应用继承默认的检查。六个已实现方法的 64 种组合逐一检查；每种方法的原有读取路径继续验证。

设置通过真实界面操作；额外的自动执行器必须对应手册的步骤编号，不能用直接改配置文件代替正常保存。安全/损坏配置测试是明确标注的异常夹具。

截图验证包含实际 SystemUI 保存与回调、Java/native 文件与目录、已有 FD、MediaStore、真实选图授权、广播和通知/剪贴板/无障碍测试内容。构造内容必须与真实系统事件分别记录。VPN/代理验证同时检查普通联网、实际代理请求和原生内存释放。

验证范围为专用 Android 16 ARM64/Vector 模拟器。四 ABI 编译分别记录，不能当成四 ABI 实机验证。无线调试开启状态在当前模拟器上无法保持，应明确标为尚无开启基线。SELinux 专项测试只在专用模拟器中建立 Permissive 与 Enforcing 对照，每次样本同时读取未注入 shell 的真实模式；测试结束恢复原模式、设置、APK、框架状态和授权，清理仅本次创建的夹具。原 0.2.0 与 0.2.1 报告保留，不能充当 0.3.0 的测试结果。
