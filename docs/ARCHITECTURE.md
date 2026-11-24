# 应用状态屏蔽 · 整合设计

本次整合名称为“应用状态屏蔽”，英文名 AppStateShield，当前版本 0.4.13。目标是让 Vector 作用域内的应用读不到指定系统状态，并可为单个应用替换设备信息读数。

0.4.13 的 DeviceProfile 增加 idsEnabled/environmentEnabled，沿用 modelEnabled/locationEnabled；新档案和缺失的网络模式默认 off。get() 先按 DeviceField 目录确认分类，再统一检查机器、分类与单项选择。with()/json()/parse()、设置草稿和恢复保留全部控制。DeviceSettingsActivity 为所有分类和字段提供开关；网络保持三档。标题显示分类状态，顶部只汇总已选/实际生效字段数量。DeviceRuntime/ModuleStatus 上报分类控制，DeviceActivity 的分类标题显示实际生效状态。模拟 SIM 构造器仅填入 get() 实际允许的字段，其他字段保留类型默认值，取消强制蜂窝选择。[具体语义](CATEGORY-GATES-0.4.13.md)。

0.4.12 在验证器的 MainActivity 和旧 ProbeActivity 中增加 EnvironmentOverview。进入前台后请求一次后台串行检查，手动刷新重新请求；后台、销毁和页面切换丢弃过期 UI 更新，正在进行的证明调用完成后清理本次密钥。EnvironmentProbe 读取固定文件、进程库、模块列表、普通状态和 AndroidKeyStore 证明；environmentprobe.cpp 提供 libc/syscall、maps/dl_iterate_phdr、属性和 enforce 读取。AttestationRecord 为无 Android 依赖、有长度与深度限制的 DER 解析器。结果经 AtomicFile 写入私有 environment-result.json，并按项打印到 Logcat/首页日志；不会调用包含主动测试夹具的 SelinuxProbe.snapshot。只新增检测器原生库，模块的 Hook/策略不变。[能力与解释](VERIFIER-ENVIRONMENT.md) 及 [原环境的不可修复原因](DETECTOR-LIMITATIONS-0.4.11.md) 为后续 Agent 的判断依据。

0.4.11 删除 APK 的 assets/native_init 清单。NativeLibraries.load 在实际请求对应库时，经 Vector 2.2 的 NativeAPI.recordNativeEntrypoint 注册后加载；截图、VPN、调试、SELinux 和机器伪装的原有加载条件保留。清单会在加载模块时提前启用 Vector 的 linker do_dlopen Hook，导致 Native Detector 7.7.0 在全部选项关闭时也出现原生闪退。延迟注册使不需要原生功能的进程保持原 linker 入口。该接口属于 Vector 框架内部桥接；框架接口不可用时，现有调用点记录原生层不可用，不把它当作屏蔽成功。

NativeAPI 的签名通过单独的 compileOnly stub 编译，不把桥接实现打进 APK。直接类型引用随 Vector 的 DEX 重命名一起改写；字符串反射不经过这条规则，在启用框架混淆时找不到原类名。

PolicyVisibility 为已保存策略或档案的应用授予只读、前缀 URI 权限；授予可见性后，PolicyProvider 仍按 Binder 调用 UID 校验请求包名，并拒绝 query/insert/update/delete 和其他 call。设置页启动、保存、应用升级与 BOOT_COMPLETED 重新建立这些授权。仅依赖 forceQueryable manifest 属性在本次 Android 16 模拟器中无效：包信息显示 true，但系统实际的 forceQueryable 列表不包含本模块。

ModuleListHooks 在明确选中 hide_module_apps=true 时才安装。它读取 PackageManager.GET_META_DATA 的实际 ApplicationInfo，仅将 xposedmodule 的 Boolean true 识别为模块，跳过目标自身；不按名称或描述猜测。可见模块集合按目标进程启动时的安装列表建立。过滤 ApplicationInfo/PackageInfo/ResolveInfo 列表，直接包名查询返回 NameNotFoundException，Intent 解析返回 null；未识别对象、普通应用和原查询异常保留。字段或机器总开关关闭后，同进程查询恢复。Native 文件读取、pm 子进程、未经过这些 Java API 的查询和框架内存痕迹不受此选项保护。ModuleListProbe 读取真实列表、直接查询和普通应用对照，DeviceRead 显示真实可见模块数量。

Native Detector 的可选 Custom ROM 检查实际命中 ro.vendor_dlkm.build.tags=test-keys。DeviceHooks 补充 system_dlkm/vendor_dlkm/odm_dlkm 的 build.id/type/tags 映射，从选中且通过机型总开关的 fingerprint 派生；这部分是模拟值，不是已核验的 OEM DLKM 固件元数据。未选择指纹或关闭机型/机器总开关时沿用真实读数。

VpnModule.INFO 对 getNetworkInfo 返回的 TYPE_VPN 对象制作副本，将 DetailedState 设为 DISCONNECTED，保留系统提供的类型和支持信息。原来的 null 结果在 Ruru 1.1.1 中触发 Vpn Connected 可疑提示；其实际代码同时检查 isConnectedOrConnecting 和空结果。getActiveNetworkInfo 和网络列表继续过滤 VPN；关闭 vpn 方法恢复原查询，原系统异常仍保留。构造副本失败会记录警告并沿用原来的空结果，因此其他系统上的兼容性仍需实测。SelinuxProbe 与六项组合断言同时检查 legacyVpnAvailable、legacyVpnConnected，防止靠丢弃对象取得假通过。

0.4.5 的 VerifierIdentity 在 Hook ModuleStatus 前校验实际包名、加载包名及当前 APK 唯一签名。DeviceRuntime 在首次 enabled 时安装设备 Java Hook，保留启动时的通知/前台轮询；关闭时恢复，已经安装的 Hook 不重复安装。BuildFingerprint 解析完整固件指纹；ModelPresets 共用根/分区转换，将 ID、TYPE、TAGS 同步给静态字段和 Java/native 属性。ProfileWarnings 只读取草稿并展示关联矛盾，不改保存值或实际 SDK。CapacityView 为 MemoryInfo、数据文件系统的 StatFs 和 File 提供数量关系一致的只读显示。验证器新增直接 API 读取，foreignProbeDebug 只供同名类的错误包名测试，不作为交付应用。详见 docs/ENVIRONMENT-0.4.5.md。

0.4.4 的 shared/native/property-read.h 共用于 devicestate、developerstate 和 selinuxstate。旧 read 先保持系统的名称缓冲区行为，再用该库原始 callback 读取完整属性名称与原值，对完整名称应用已有过滤器。替换的只读值超过 91 字节时写入 Android 的旧接口兼容提示；短值正常返回。替换会清零完整 92 字节缓冲区。callback 保留完整预设值及同步调用时的字符串生命周期，字段关闭后沿用系统原结果。本次不修改属性区内存布局和系统属性。

ModelPresets 保存小米 14 国际固件和本机 vivo X200 Pro mini 实测数据，区分根属性与分区属性。DeviceRuntime 的 Java 属性读取和 nativeUpdate 共用同一属性转换；字段被手工修改时尊重自定义值，字段或机器关闭时恢复原值。旧小米占位数据按已知模式定向迁移，移除的 OPPO 档案转为自定义；未知字段、个人标识和位置/网络选项保留。

DeviceProfile schema 1 保存 locationEnabled、regionId、regionName、regionOverrides 和 networkMode。0.4.13 的新/缺失网络模式为 off，四个布尔分类控制缺省 false。位置、标识、机型、其他环境及网络参数均经过机器、分类、字段三层条件；MCC/MNC、SIM 和基站归入 network。有卡模式不再绕过蜂窝字段选择；未选参数不填入虚拟对象，Wi-Fi/蓝牙同样按字段选择。所有参数保存后供读取使用，getter 不生成随机值。

DeviceHooks 为 simulate 构造一个 slot 0 订阅、READY/PRESENT/LOADED 卡状态、已注册的 CS/PS LTE ServiceState 和包含一条注册小区的 CellInfo。同步读取、异步回调与 Parcel 使用同一保存参数。no_sim 返回无卡、空订阅、未知移动网络、无服务和空小区；off 委托系统原实现。各档由机器总开关统一约束。四 ABI 构建与 API 36 模拟器实测分别记录，真实厂商服务兼容性不能从 AOSP 推断。

ChinaRegions 从 APK 内 china-regions.tsv 读取离线层级和代表坐标，packet 生成确定性位置参数；生成器 build-region-data.py 和许可证一起保留。地区选择是草稿操作，保存前不发布，也不打开位置开关。检测器共用 DeviceField 分类并显示模块快照中的 locationEnabled。

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

机器伪装另存 DeviceStore，默认关闭；不加入 Methods 的默认开启集合。DeviceField/DeviceProfile 是模块和验证器共用的字段目录与档案格式。Provider 只返回调用 UID 自己的设备档案。档案包含 enabled、selected、values、preset 和单调递增 revision；格式错误的已选字段导致档案关闭。2026-11-19 起，`DeviceProfile.preset()` 创建的新档案默认选中除 `drm_id` 外的全部 46 个字段（设备标识 9/10、网络与基站 15/15、机型与系统 13/13、位置 3/3、其他环境 6/6），但所有分类总开关仍关闭，默认生效字段为 0；解析已有档案时不迁移或补选字段。

DeviceRuntime 同样在 Application.attach 前启动，Java 适配器以本地不可变档案判断字段是否选中。开启时加载 devicestate，关闭时清除它的替换表并还原最初捕获的 Build 字段。设置保存原子提交后通知当前包的 URI；有可见 Activity 时独立线程每两秒查询，最后一个 Activity 停止后取消周期查询，重新显示时立即刷新。后台服务保留配置通知，服务新进程仍在 attach 前读取配置。只在成功读到新版本后替换档案。Getter 本身不调用 Provider。旧六项屏蔽仍只在冷启动读取策略。

DeviceHooks 使用明确的 Android 类型与字段、厂商类名及 MSA IdSupplier 接口元数据安装 Hook。接口抽象方法本身没有执行入口，因此识别具体供应者实现；MdidSdk/Helper 初始化时根据回调参数类型接入监听器，在交付供应者前安装其具体方法。类加载检查用于补充动态 SDK。Location 的 Parcel 写入和 toString 用修改后的对象副本，保留原对象的时间和提供者信息；位置 extras 可能带有真实位置信息，副本会清除它们。Resources metrics 返回副本，避免直接污染原始资源配置。

devicestate 通过 developerstate/selinuxstate 的属性过滤器以及 vpnstate 的网卡过滤器组合已有 Hook，避免 Vector 重复 Hook 同一 native 符号。未加载对应库时独立安装；使用原子不可变表更新属性和网卡地址，不更改网卡列表所有权或 freeifaddrs。截图 syscall/clone 与 SELinux 文件读取处理保持原实现。

DeviceRead 用后台任务逐项实际读取。电话 API 在同包、同 UID、未导出的 PhoneReadService 辅助进程中调用，仍由 Vector 注入同一包的配置；返回值携带辅助 PID 和配置版本，版本不一致显示读取错误。每次批量读取最多等待 800 毫秒，回复后结束辅助进程，释放没有返回的电话 Binder 请求。主检测页的 PID 保留；它不把配置值当作电话读数。Future.cancel 不能撤销同步 Binder 请求，原实现会在后台留下请求，系统因无法冻结 Binder 而结束主进程，现用辅助进程处理这个实际问题。其他接口仍在检测页进程读取，有限线程池保留超时任务。DeviceActivity 前台两秒采样、后台暂停，同时显示时间、PID、变化与失败。旧状态、SELinux 和截图 Probe 通过 ModuleStatus.json 保留完整注入标记，包含机器伪装的启用状态和修订号。配置标记和读取值分开展示；静态内联及 SDK 缓存的更新不作保证。

模块设置保存在私有 SharedPreferences 中，更新必须使用同步原子提交。只读 ContentProvider 向调用方提供其自己的配置；调用方 UID 必须拥有请求的包名。写入仅由模块自身 UI 完成，其他应用无法改配置，也无法读取另一应用的配置。

模块入口在 `Application.attach(Context)` 原方法执行前取得配置，并安装被选中的 Java/native Hook，确保目标应用的 `attachBaseContext`、ContentProvider 和 `onCreate` 使用同一份配置。主模块自身不注入，避免配置服务递归。正常同包多进程共用配置。

整合保留原有三个 native 库，并新增 selinuxstate，均只在对应方法启用时加载。截图 syscall 汇编分派、原生列表成对释放和 Vector 链接器映射兼容处理保持不变。VPN 与网络代理拆开；开发者选项与调试状态拆开。关闭调试方法时，Java/native 调试属性都保持原值。

SELinux 在同一 Application.attach 前安装。Java 的 android.os.SELinux.isSELinuxEnabled/isSELinuxEnforced 返回 true；native 的 security_getenforce/is_selinux_enabled 返回 1。已存在的 ro.boot.selinux 文本返回 enforcing，缺失的属性和调用方默认值保持原样；这个启动属性不能替代真实运行时模式。新库通过 RTLD_DEFAULT 和 Vector 的库加载回调取得符号；系统私有 libselinux 已由 zygote 加载但应用 namespace 不允许 dlopen 时，从该库实际加载的 ELF 动态符号表定位已定义函数。共用解析代码在 shared/native/loaded-symbol.h，不加载或复制系统库。

native read、__read_chk、pread/pread64、readv 先使用真实 FD 读取，只对 /sys/fs/selinux/enforce 或 /selinux/enforce 的实际返回字节将 0 改为 1。通过 /proc/self/fd 识别目的文件，不缓存 FD 编号；dup、关闭后复用、相对路径和符号链接沿用真实文件语义。失败、EOF、偏移和 errno 保留；普通同名文件不改。Bionic 的 FILE refill 经过已覆盖的 read 时，fread/fgets 直接消费已经过滤的缓冲字节，避免每次缓冲读取重复解析 FD；read 未能覆盖时保留原 fread/fgets 包装。不完整末项仍按真实字节过滤，不把它误算成完整项。系统模式、安全上下文、写入权限都不修改。

Vector 不允许重复 Hook 同一个函数。截图库与开发者库提供两个内部过滤器注册入口，仅接受各自已安装的原生符号；SELinux 使用这些入口追加读取/属性过滤。截图关闭或调试关闭时，相应入口不存在或未安装，SELinux 自己安装该组 Hook。注册使用原子函数指针，不改截图 syscall 汇编、clone 分派或原有内存释放逻辑。

SELinux 的 native 入口使用与 0.2.1 相同的两类 ARM64 跳转识别，保留加固库的外部跳转。直接 syscall / 内联汇编、未注入子进程、其他挂载路径、未 Hook 的读取函数以及保留入口不属于已验证的保护路径。

模块 0.2.1 在 ARM64 安装截图 native Hook 前检查现有入口。对于已跳到其他库或匿名代码的 `B`，以及 `LDR Xn, [PC+8]; BR Xn; .quad target`，保留应用已有跳转；跳转仍位于同一库的普通包装函数继续处理。跳过的符号名写入日志，供兼容检查使用。此处理不使用应用包名名单，不改变配置或安装时机，也不改 syscall 汇编。只识别这两种 ARM64 入口；其他跳转形式及其他 ABI 的加固兼容尚未验证。保留入口的原生读取没有完整保护，不能以应用正常启动或 Hook 数量代替截图屏蔽证据。

2026-11-19 的原生兼容修复由 NativeLibraries 在首次需要原生方法时加载 nativecompat。ARM64 入口使用 shared/native/entry-hook.h：原位只发布一条 B 指令，但备份并重定位完整 16 字节，保留正阻塞在 syscall 的线程返回指令。首次原生库加载期间临时适配 DobbyHook，覆盖 recordNativeEntrypoint 和随后执行 native_init 的 loadLibrary，库加载完成后恢复该入口；加载器 Hook 的备份仍保持有效。截图、VPN、debug、SELinux 的原生方法继续按策略安装，不按银行包名豁免。

nativecompat 从已经加载且导出 DobbyHook 的框架 ELF 确认可执行段，再读取当前 libart.so 的磁盘 ELF。elf-code-view.h 按符号表和 PT_LOAD 做长度检查，只记录明确跳往框架可执行段的 ARM64 B、LDR/BR 或 ADRP/ADD/BR 入口及磁盘原始 16 字节。无法读取、没有本地符号表或无法确认所有者时不猜原指令。实际执行页保留 Hook；libc process_vm_readv 和 libc syscall 的 process_vm_readv 读取自身进程后，按两组 iovec 的实际字节顺序还原已记录的代码视图，保留返回长度、错误、普通内存和其他进程的读取。只有读取结果仍匹配已记录的改写指令时才替换，不覆盖后来第三方修改。其余 syscall 用汇编直接跳回备份，保持 clone 的调用栈和六个参数。机器伪装的 seccomp 代理仍只随机器档案启用，本兼容层不启用它。

该视图不能隐藏真实 maps 中的框架注入，也不处理应用内联 svc 或任意直接代码读取。它针对建行已确认的 ART 入口比较路径；原生夹具验证与银行实际启动须分别报告。夹具把本地 .symtab 函数改为 Vector 形状的跳转，加载正式构建的 nativecompat，通过 scripts/native-compat-test.py 运行；不能把夹具当作 vivo ROM 上的运行验证。

验证应用提供“是否注入/实际安装的方法”标记，与“存储的配置”分开显示。标记不是实际状态屏蔽的替代证据，仍需真实系统状态和普通操作对照。

截图日志页在 ContentObserver 注册、FileObserver startWatching 完成后才显示相应来源就绪。FileObserver 监听 CREATE、CLOSE_WRITE 和 MOVED_TO，覆盖不同截图保存方式。Java FileObserver 共享 inotify 线程；新日志页开始监听前，先停止上一日志页，避免旧页延迟 onStop 删除新页对相同目录的 watch。页面停止时只清除自己持有的 Signals.listener。

截图方法在注册 MediaStore observer 时保存可见普通行的元数据快照。系统通知没有图片 ID 时，只有普通行实际新增、删除或修改才放行；仅截图变化不会改变该快照。快照查询失败或无权限时仍抑制不明通知。普通行很多时，集合通知会增加一次元数据查询的成本；没有扫描图片内容。嵌套 dispatchChange 只在最外层判断，避免同一次通知被重复比较后误拦截。

## 设置交互

0.4.1 的 DeviceOverview 在检测首页及旧状态页直接显示双卡 IMEI、Android ID、OAID、序列号与型号。DeviceActivity 将设备标识排在机型之前，可搜索共享目录的全部 46 项，并额外展示 Java/native MAC 等入口；DevicePresentation 显示权限拒绝、服务缺失、超时及占位地址。观察值只来自 DeviceRead。DeviceSampler 共用单线程实际采样，各页暂停时取消周期请求并丢弃过期回调；电话服务的解绑完成后才执行下一份采样。原始 JSON 仍可展开，传统截图日志不改。

DeviceSettingsActivity 的每个字段均可单独填入预设，随机标识取新合成值；只更新当前字段草稿。行内随机刷新同时选中该字段，与弹窗生成行为一致。字段目录、档案格式、Provider 和 Hook 不变。

验证器首页的 ObservedState 只读取 ConnectivityManager、Settings.Global 和 SELinux API/enforce 文件，每 2 秒在后台线程刷新，页面退出前台后停止轮询。它不调用包含代理请求、文件写入等测试夹具的完整 Probe。异常单独显示无法读取，模块注入提示与状态值同时可见。SELinux 优先使用 enforce 文件的实际 0/1；文件不可读时，Java API 的 false 可能来自 security_getenforce 失败，显示“模式无法确认”，不能据此断言 Permissive。

ScreenshotSession 与传统来源信号计数分开。相同文件路径和相同 MediaStore ID去重；不同入口的信号在 2 秒窗口内合并，重复官方回调、同一入口的不同图片仍增加次数。无身份的重复浮层信号在窗口内合并，因此截图次数标为估算。最近身份最多保留 1024 个，超过后淘汰最旧项。保存状态时序列化会话以保留旋转/进程重建期间的次数和去重信息；后台不新增信号，清空日志或重启监听不重置会话，新页面/冷启动使用新会话。

模块页显示默认策略、定制列表与“添加应用”。应用选择支持按名称/包名搜索和系统应用筛选。应用详情显示每种方法的用途、开关和保存按钮；添加应用时默认全部开启。

保存、取消、返回、未保存修改提示、恢复默认、重复选择、卸载后的条目、旋转/进程重建、列表排序和语言切换都需要人工手册覆盖。取消不得产生配置；恢复默认不得影响其他应用。SELinux 显示独立开关及“向应用返回强制执行状态，保留系统实际模式”说明。

## 验证要求

0.4.10 的 model 分类仅保留“按预设机型填写参数”一个按钮，按钮显示当前预设名称。choosePreset 选择预设后填入下方字段；原 model 刷新入口及其重复分支移除。统一刷新仅用于 ids/network。模型总开关及其他分类参数不因填写预设而改变。

0.4.8 的机型预设只由 DeviceSettingsActivity 的 model 分类显示。选择小米/vivo 时，通过现有字段目录和 DevicePackets.group("model", preset) 更新机型、系统和屏幕字段；不再创建整份随机档案替换当前草稿。设备标识、网络、位置、其他环境、未知字段及各总开关保持原选择。0.4.9 删除顶部随机标识操作，顶部卡片只显示整体状态；统一刷新位于设备标识、网络与基站、机型与系统各自分类中，只处理对应分类。

0.4.7 增加进程内属性文件视图。property-area 按 Bionic 的 trie、prop_info、serial 与长值偏移布局生成只读快照，清除被替换的旧值。读取保留应用原 FD，仅覆盖变化字节；只读 mmap 使用密封模块文件的私有映射。原始 read/pread/readv/preadv2/mmap 由 seccomp user-notification 代理适配，通过 TSYNC 同步已存在的线程。代理回调只使用准备好的快照和 raw syscall helper；raw 指令地址允许代理执行自身 I/O。该过滤器不能卸载，关闭档案后代理继续放行；no_new_privs 和 seccomp 状态可被同进程观察。

2026-11-19 的首次启动排查发现，代理在每次普通读取前读取 /proc/&lt;tid&gt;/status，叠加 FD 路径解析，给 SecurityGuard 初始化增加了大量文件操作。代理现用 /proc/self/task/&lt;tid&gt; 的内核目录成员关系验证线程，使用预先保存的 device/inode 识别属性文件和本进程 mem，不缓存可复用的 FD 编号。libc 读取和直接 syscall 共用 BrokerSnapshot；普通文件经 fstat 后立即返回，属性区和代码视图使用已准备的快照。向量描述符复制走 raw process_vm_readv，不进入包含分配和动态符号解析的公共包装器。自身 mem 的代码视图按安装相反顺序还原，并接入 nativecompat 已确认的 ART 入口视图；后续第三方改写仍保留。NativeBrokerTest 使用实际 seccomp 代理验证线程/子进程、readv/preadv、原错误、dup/EOF、普通管道和关闭后原值。

2026-11-20 的 vivo 原生采样确认，libunwindstack 使用 Bionic 保留信号 33 暂停代理线程后，Signal Catcher 对自身内存的读取又等待该代理，导致栈采集循环等待。awaitListener 在发布 ready 之前，只为这个不受 ART 管理的代理线程用 raw rt_sigprocmask 屏蔽信号 33；pthread_sigmask 会移除保留信号，不能用于此处。应用线程的信号掩码保持原样。该信号无法再采集代理线程的栈，采集方需按原超时处理；不能据此认定应用没有其他启动等待。NativeBrokerTest 对代理发送信号后继续检查读取，并确认调用线程仍可收到同一信号。vivo 闲鱼是否能完成首次初始化仍须完整四步实测。

同日的自然 ART 栈确认，许可协议回调等待 SecurityGuard 的初始化节点，持锁线程在 FILE 读取路径中。设备层与 screenshot 的 appstateshield_set_device_file_views 增加 KernelRead 回调：已由 screenshot 包装器接管的 read/__read_chk，先完成截图 FD 检查，再从设备层的 raw 指令读取原 FD，在调用线程上应用同一 BrokerSnapshot 与 SELinux 过滤，避免再等待一次 seccomp 代理。__read_chk 超出容量时仍调用原 fortify 函数。应用直接发出的系统调用、未接管的入口及 mmap 仍沿用代理；没有按 libc 地址或 FD 编号放宽过滤。

已经缓存的属性区仅重映射可安全隔离的只读页，避开全局 serial、dirty backup 和共享可变属性所在页。旧映射被读取前不一定经过任何 Hook，因此保留页仍可读到真实值；检查结果必须列出 remappedPages/retainedPages，不能将新 FD/mmap 通过推成旧 CPU 缓存页也通过。

code-view 记录本 APK 成功安装的 native Hook 前后字节。经 /proc/self/mem 读取时，仅对仍匹配本模块已安装字节的范围返回原字节，后续第三方修改继续可见。直接执行页上的指令和 CPU 数据读取仍访问当前 Hook 字节，未提供受信任的代码隔离。

AttestationHooks 复制请求参数，按 DeviceProfile 的实际生效字段删除 KeyMint/Keymaster 标识标签。challenge、密钥授权、实际证书和证书签名保持原样；不生成其他设备的证明，不替换服务器判定。ModelPresets 派生属性及硬件标识移除逻辑均通过 get() 尊重 machine/model/field 开关。modelEnabled 默认 false，width/height/density 与机型系统字段同属 model。设置草稿、保存、进程重建、统一刷新和预设切换均保留总开关。

0.4.7 只运行新增的属性文件/系统调用、代码读取、证明请求和机型开关用例，历史矩阵保留原 APK 来源。scripts/incremental-environment-test.py、scripts/model-gate-incremental.py 使用独立 debug 入口，避免调用完整电话采样器。详细原因与证据见 [本版说明](PROCESS-PRIVACY-0.4.7.md)。

0.4.6 的设备属性对象适配见 [只读对象说明](PROPERTY-OBJECTS-0.4.6.md)。devicestate 通过 HandleAdapter 与本 APK 已加载的 developerstate/selinuxstate 共用指针映射，选中 ro.* 属性使用密封共享文件中的不可变对象。原始属性区及系统服务作用域不变，机器档案仍由现有 Provider 校验 UID 后读取。

先建立无保护的真实 VPN、开发者/USB、SELinux、系统截图基线，再执行默认、定制空集合、单方法、全部关闭、逐项更改、两个应用相反配置和第三个应用继承默认的检查。六个已实现方法的 64 种组合逐一检查；每种方法的原有读取路径继续验证。

设置保存、草稿和输入校验通过真实界面操作。组合及全字段还原用例在代表性 UI 保存核对后使用专用模拟器批量配置，保留实际读取断言与原档案；异常夹具单独标注。执行和结果复用规则见 docs/TEST-EXECUTION-POLICY.md。

截图验证包含实际 SystemUI 保存与回调、Java/native 文件与目录、已有 FD、MediaStore、真实选图授权、广播和通知/剪贴板/无障碍测试内容。构造内容必须与真实系统事件分别记录。VPN/代理验证同时检查普通联网、实际代理请求和原生内存释放。

验证范围为专用 Android 16 ARM64/Vector 模拟器。四 ABI 编译分别记录，不能当成四 ABI 实机验证。无线调试开启状态在当前模拟器上无法保持，应明确标为尚无开启基线。SELinux 专项测试只在专用模拟器中建立 Permissive 与 Enforcing 对照，每次样本同时读取未注入 shell 的真实模式；测试结束恢复原模式、设置、APK、框架状态和授权，清理仅本次创建的夹具。原 0.2.0 与 0.2.1 报告保留，不能充当 0.3.0 的测试结果。
