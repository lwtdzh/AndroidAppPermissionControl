# 建行启动故障重新分析

日期：2026-11-19。结论：此前“vivo 因 MTK libc 切换到陌生库白名单检测，代码无法修复”的说法没有证据，需撤回。**17:25 以后真机候选的 0x88c 崩溃，可以定位到加固库发现 ART 的 ClassLinker::RegisterNative 入口被改写后主动崩溃。** 它不同于早期 read/mmap 包装器递归，也不是已有证据证明的 APK 路径白名单拒绝。

本轮读取真机现存二进制、配置元数据与历史 tombstone；启动测试只在 ScreenshotShield_API36 / emulator-5584。没有安装新 APK、重启手机、杀 zygote、改变真机作用域或写入真机配置。模拟器仅修改临时建行作用域及策略，结束后逐字恢复 XML 与原作用域。没有修改保护代码、提交或推送。

## 两端用了什么

两端当前 AppStateShield 均为前一轮的 ccb-fullskip-v2.apk。以下 SHA-256 来自本轮读取设备上的原始文件，而不是从版本名称推断。

| 文件 | vivo 与 emulator 是否逐字相同 | SHA-256 |
| --- | --- | --- |
| Vector Zygisk ARM64 库，2.2 / 3080 / 88f8e1fa | 相同 | 8642b0ed3ad8a2852d5119902dba3768529b8529f5cd94c4e63ce9aafc959a7c |
| Vector framework/vector.dex | 相同 | b75c889406507bae5f5f580efea778df6e2f556944a4bddc9d8f628ea0f3b4fd |
| 建行 9.8.0 / 2412 APK | 相同 | cd4f1f37ddcecb51fab8ea9c4895a92022b44e827e3c8a9b368bebf843f1449c |
| 建行 libDexHelper.so | 相同 | f79e2da442dac3200e92a3c41333fa918d2e029b37aefcd16b2ddd064cddaf6e |
| 当前 AppStateShield APK | 相同 | c5a43a2c36010a3b759f0d26ec42777f07becc2737a8cf03dec014f170d6103a |

Vector daemon.apk 不同；它负责配置服务，不等于两端 ART 注入库版本不同。不能由上述相同文件证明所有服务配置、模块、系统库和运行环境都相同。

| 系统库 | vivo SHA-256 | emulator SHA-256 |
| --- | --- | --- |
| libart.so | d690004ba2eeb08081a3d68d33a1d194876ebb10e9189f49c77b4983a20182cb | 72d5d4b78d8b6cead8d5bddb1ba4a44113f4450c12c239d7530407e8f5bef989 |
| libc.so | dda1c005db4ea4025e0e7c01945ea31b191c2599f63d99a2a05ebbe1b7da06ca | d3f8599b8b3f00101a31f94ac170ceb5875ee8446c201cb18382b2e02df84301 |
| linker64 | 6ddcde1a12006d2deda4ab99beb648f04cef9bf49aae0380b32ace80b90e3269 | 30ed9bea070250e0b080c8a84d8398baab1b4eb95a90bfced82a94d5f235144b |

系统库不同是事实。仅凭哈希不同不能推导“MTK 修改了 libc 的检测策略”，也不能推导 Secneo 按 libc Build ID 切换模式。

## 0x88c 为什么会出现

使用建行同一 Build ID 685f3c28bea88e365e33779cfa4c13f140ad943c 的 libDexHelper.so 反汇编，按地址核对真实指令；没有把反汇编输出中最近的 safejni 符号名称当作整个后续代码的函数名。

1. 0x53bec 起的检查构造 ART 函数名称，并在 0x543c4–0x544a4 依次调用 0x52a1c，库名固定为 libart.so。检查包括旧版 ArtMethod::RegisterNative、新版 ClassLinker::RegisterNative、UnregisterNative 和 FixupStaticTrampolines。
2. 0x52a1c 查找目标函数符号，通过原生 openat/read 等读取 ELF，映射磁盘文件；0x52c24–0x52c34 调用 syscall 270，即 ARM64 process_vm_readv，读取本进程该入口的 16 字节。
3. 0x52c50 调用 memcmp。字节相同返回 0，不同返回 1；无法查找或读取有独立错误返回，调用者不会把这些错误自动视为“不一致”。
4. 任一对应检查返回 1，进入 0x544b8：生成事件值 0xb6a2888d，调用 0x31c64。
5. 0x31ec0–0x31ee8 的故障分支将事件值与 0xfff 相与再清掉低两位，得到 0x88c；明确执行 MOV SP, X0、MOV X30, X0，其中 X0=0，然后 BR X12。

因此 PC=0x88c、SP=0、LR=0 不是本轮所谓“safejni 自递归”。这是主动构造的崩溃现场。仅看系统输出的 null pointer dereference 会遗漏这段代码。

## 真机具体发现了什么

本轮从真机现存 tombstone_20、29、31、00 提取代码现场，时间分别为 11-18 17:25:22、18:14:24、18:18:45、18:20:40。四份现场 X3/X5 对应磁盘原字节，X4/X6 对应内存字节；核对 ARM64 memcmp 的字节顺序后，原字节都精确匹配 vivo libart.so 中：

**art::ClassLinker::RegisterNative(Thread*, ArtMethod*, const void*)，ELF 地址 0x3a2a30。**

原前 16 字节：

```text
ff0302d1 fd7b03a9 f92300f9 f85f05a9
SUB SP, SP, #0x80
STP X29, X30, [SP, #0x30]
STR X25, [SP, #0x40]
STP X24, X23, [SP, #0x50]
```

tombstone_31 的实际内存前 16 字节：

```text
f199f7f0 31e21191 20021fd6 f85f05a9
ADRP X17, <目标页>
ADD X17, X17, #0x478
BR X17
STP X24, X23, [SP, #0x50]
```

这是真实的入口改写。对应进程 libart 的可执行映射基址为 0x6dea603000，函数地址为 0x6dea9a5a30，解码跳转目标为 0x6dd9ce4478。目标位于 0x6dd9c2e000 起、长度 0x128000 的匿名可执行映射；减去基址，偏移为 **0xb6478**。设备上 Vector ARM64 ELF 的动态符号表正好给出该偏移是 LSPlant ClassLinker RegisterNative 包装器。

另外三份现场的 ASLR 地址不同，但都解码为所在匿名 Vector 映射基址 + 0xb6478。事件值、原字节、改写指令和目标包装器相互对应，支持这一具体归因。

完整检查逻辑可能还有其他拒绝条件。本轮只证明上述真机候选实际触发的这一项，不声称已经排除加固库所有其他检测。

## 为什么模拟器没有触发同一检查

vivo libart.so 保留 .symtab 和 .strtab；上述 RegisterNative 符号以本地符号保存在 .symtab，值为 0x3a2a30。模拟器 libart.so 没有普通 .symtab/.strtab，仅有动态符号表和 .gnu_debugdata 压缩调试信息。上述函数没有以相同名称在模拟器动态符号表导出。

本轮离线运行 **原 libDexHelper.so 的 0x41008 ELF 符号解析函数**，ARM64 指令由 Unicorn 执行。open/read/stat/malloc 等只接本地文件夹具，不连接手机、不运行检测或崩溃函数：

| 输入文件与目标符号 | 原解析器结果 |
| --- | --- |
| vivo libart.so，ClassLinker::RegisterNative | 匹配 1 项，地址 0x3a2a30 |
| emulator libart.so，同一符号 | 匹配 0 项，地址 0 |

这比“两个 libc 哈希不一样”更接近实际差异。加固库这条解析路径找不到模拟器的目标符号，后续无法比较同一入口；Vector/LSPlant 有自己的符号解析能力。**模拟器没有触发这一项检查，不证明其 ART 入口没有 Hook，也不证明 vivo 使用另一版本 Secneo。**

这里的离线执行是解析器证据，不能替代真机开启/关闭模块的运行验证。

## 本轮模拟器启动对照

使用设备上现有 fullskip-v2 字节，没有构建或安装另一 APK。每项冷启动后在 3、6、9 秒采 PID，通过 UIAutomator 及截图核对页面。三项连同还原累计 37.340 秒。

| 条件 | 实际策略日志 | 观察 |
| --- | --- | --- |
| 建行移出所有相关模块作用域 | 没有 AppStateShield 策略日志 | PID 24088/24107 三次不变，显示首次协议页，没有模块原生库映射 |
| 建行在 AppStateShield 作用域，六项全关，机器伪装关闭 | Policy loaded=true enabled=[] | PID 24416/24445 三次不变，显示首次协议页，没有模块原生库映射 |
| 建行在作用域，六项全开，当前源码仍 fullskip | Policy loaded=true enabled=[screenshot, vpn, proxy, developer, debug, selinux] | PID 24733/24761 三次不变，显示首次协议页，存在模块原生库映射 |

第三项是**带包名豁免的候选启动观察**，原生保护已跳过；不能用于证明“六项完整保护且能启动”。三项没有同意条款、登录或进入实际银行业务。

真机本轮只读取现存故障，未重新把建行加回作用域。因此“纯空模块在 vivo 上是否同样触发”仍须单独验证；前面移出作用域的结果不能回答这个问题。

## 前一轮哪些结论需要纠正

| 旧说法 | 本轮核对 |
| --- | --- |
| Vector 在两端版本不同，或 Secneo 版本不同 | 注入库、框架 DEX、建行 APK 与加固库哈希均一致；不能这样归因 |
| Secneo 遇到 MTK libc 切换到陌生 APK 路径白名单 | 没有这条分支的证据；实际 0x88c 故障对应 ART 入口字节比较 |
| 全跳模块等于没有任何新增 Hook | false。Vector 的 ART 框架 Hook 仍存在；NativeLibraries.java 第 33 行仍调用原生注册接口，该接口还会安装 linker do_dlopen Hook |
| 六项全关后真机也崩，证明空模块不兼容 | 旧日志实际为 Policy loaded=false enabled=[全部六项]。旧配置写入没有形成有效对照 |
| Provider 不可用只是因为模块应用没打开过 | 未证明。普通 Provider 可按需启动；本轮真机注册信息存在，vivo 用户状态还有 vHidden=1。具体可见性/服务原因需要独立排查 |
| maps 中出现模块 APK，证明崩溃由路径白名单触发 | maps 证明映射可见，不证明哪条检测造成崩溃；模拟器成功候选也有这些映射 |
| memfd 加载能使进程内模块绝对不可发现 | 未证明。匿名映射也可被枚举，ART 入口改写也不会由改变库文件 backing 自动恢复 |
| 跳过 open/stat/readdir/inotify 不削弱屏蔽 | false。文件存在性、目录及通知路径已经不再经过相应 Hook；保留 read 不能覆盖这些信号 |
| syscall Hook 覆盖任意内联系统调用 | false。Hook libc syscall() 不会自动拦截其他代码自己执行的 SVC |
| fullskip 已完成最终验收 | false。截图/VPN/开发者/SELinux 的原生安装入口返回，原生能力明确缺失；真机仍有 0x88c 故障 |

Vector 官方 v2.2 README 描述为基于 LSPlant 的 Zygisk ART Hook 框架。前面用“LSPosed 在 fork 前、Vector 通过 ptrace 在 fork 后”解释兼容性，没有对应源码或时序证据，也不是上述字节比较差异的解释。本轮不继续沿用。

## 是否有继续修复的方向

**“无法修复”尚不成立。** 现在可以针对已定位的 ClassLinker::RegisterNative 完整性检查做兼容性实验，不需要先假定必须实现一个自制 ELF 加载器。

可探索的方向包括框架侧调整 ART Hook 实现/安装方式，或者在确切的检查读取路径上提供一致的原始代码视图。二者都需要实测：前者不得破坏 JNI 注册与 Hook 恢复，后者须考虑 process_vm_readv、直接系统调用及后续检查。只取消 RegisterNative Hook、关闭六项保护或把建行移出作用域，均不能作为“能力不减”的最终修复。

接下来应先修正过早的成功结论，排除无效的策略读取对照；再在专用模拟器用对应 ART 夹具复现已经证实的检查并验证修复。最终是否能在 vivo 保留全部保护启动，仍须用受控真机证据证明。

## 2026-11-19 修复结果与模拟器验证

上述“本轮没有可交付的已修复 APK”只对应修复前状态。后续已实现并验证一个不使用银行包名豁免的候选，产物为 `verification/AppStateShield-bank-codeview.apk`：

- 签名后 SHA-256：`36500e260662238fc3962cc27c2404db685796b2653922995d06d74377a11490`
- 未签名 APK SHA-256：`eacd14dae8f3a918730591c39bf6daa8e1be860726b7b3465dd5b2b8e9309110`
- 正式 `libnativecompat.so` SHA-256：`671ff920ce7139990a7e46bab53fe96d235e0f9f0e91fc4234cb24271d0d28a8`

### 修复分成两层

第一层处理已确认的 ART 入口比较。`nativecompat` 先从已加载且导出 `DobbyHook` 的框架 ELF 确认可执行段，再读取磁盘上的 `libart.so`。`elf-code-view.h` 只接受同时满足以下条件的 16 字节入口：符号位于可执行 PT_LOAD、当前入口是跳往框架可执行段的 ARM64 `B`、`LDR/BR` 或 `ADRP/ADD/BR`，并且磁盘字节与当前内存字节不同。实际执行页保留 Hook；进程通过 libc `process_vm_readv` 或 libc `syscall(270, ...)` 读取自身代码时，仅把成功返回且仍匹配已记录 Hook 的片段替换为磁盘原指令。其他进程、普通内存、错误参数、空 iovec、部分读取和分段位置都保留内核结果。

第二层处理修复过程中新确认的 mmap 递归。把 DobbyHook 适配保持到 `System.loadLibrary()` 返回，而不是在 `recordNativeEntrypoint()` 后立即恢复。这样 `libshield.so` 的 `native_init` 安装 mmap、syscall 等入口时会使用 `entry-hook.h`：原位只有一条 `B`，独立跳板保留完整 16 字节前缀和重定位后的原指令。修复前日志显示 mmap 为 Dobby 的 16 字节 `LDR/BR`，建行栈在 `libDexHelper.so` 的 0x51620 / 0x51750 递归；修复后 mmap 和 syscall 均为原子入口，日志分别为 `atomic=1`，递归消失。

代码中已经删除按 `com.chinamworld.main` 跳过 Hook 的实现，也没有新增其他银行包名判断。截图、VPN、代理、开发者选项、USB/无线调试、SELinux 六个方法仍按同一策略安装。

### 原生夹具

`scripts/native-compat-test.py` 从正式 APK 中取出 `libnativecompat.so`，在 emulator-5584 上运行命令行夹具。夹具构造本地 ART 符号和 Vector 形状的 ADRP/ADD/BR 跳转，验证：

- libc syscall 与 `process_vm_readv` 读到磁盘原字节，但实际调用仍进入 Hook；
- 两组 iovec 分段不同、零长度、部分返回、EFAULT、EINVAL、普通内存和其他进程读取均符合预期；
- 后来的第三方改写不会被旧视图覆盖；
- 阻塞在 read 中的线程返回后仍执行原指令；
- 另一组件覆盖完整 16 字节入口时，备份和恢复仍成立。

`native-compat-test` 与 `entry-hook-test` 均通过，结果写入 `verification/native-compat-20261119-results.json` 和 `verification/native-compat-final-20261119.log`。这是 SDK 形状夹具，不冒充 vivo ROM 的实测。

### 两个银行的冷启动

最终同一份签名 APK 在专用 emulator-5584 上测试，六项全部开启，每次冷启动后 3、6、9 秒 PID 保持一致，并显示首次隐私/协议页。脚本结束后恢复原模块 APK、策略、机器档案、作用域和 UI 临时文件。

| 应用 | 用例目录 | PID 观察 | 耗时 |
| --- | --- | --- | --- |
| 建行 `com.chinamworld.main` | `startup-1795070866143980000` | 5649/5681 三次一致 | 12.429 秒 |
| 动卡空间 `com.citiccard.mobilebank` | 同一用例目录 | 5941/5958 三次一致 | 12.197 秒 |

汇总在 `verification/bank-codeview-startup-20261119.json`。首次协议页只证明启动到该页面，没有同意条款、登录或执行业务操作。模拟器 libart 缺少 vivo 那个本地符号，因此模拟器银行启动不能单独证明 vivo 的同一条 ART 检查已在真机通过。

### vivo V2419A 真机启动

用户明确授权后，在 V2419A（Android 36）上安装同一份候选 APK，临时把两个银行加入模块作用域并写入六项全开策略，测试结束后恢复原模块 APK、策略和作用域。脱敏结果保存在 `verification/vivo-bank-codeview-20261119.json`，完整日志、截图和快照保存在仓库外的 `~/Library/Application Support/ScreenshotShield/bank-codeview-vivo-20261119/`。

真机准备过程中有两个系统行为需要区分：vivo 锁屏会使银行进程无法解析模块 Provider，进入默认全开兜底；vivo 的应用分身选择器会拦截模块设置 Activity，使 URI 可见性授权没有执行。手动解锁并通过 `DoubleAppResolverActivity` 进入模块设置后，`PolicyVisibility.restore()` 正常授权。这些是测试编排问题，不是模块 Hook 崩溃；前几次失败现场均保留在私有目录，最终结果以下方通过记录为准。

| 应用 | PID 观察 | 策略读取 | 原生入口 | 前台窗口 | 结果 |
| --- | --- | --- | --- | --- | --- |
| 建行 `com.chinamworld.main` | 首次采样有短生命周期辅助进程，后两次均为 6236/6273 | `Policy loaded=true`，六项全开 | mmap、syscall 均 `atomic=1` | 目标包 | 通过，无 Fatal signal |
| 动卡空间 `com.citiccard.mobilebank` | 7403/7445 三次一致 | `Policy loaded=true`，六项全开 | 应用自身 mmap 外部跳转按兼容规则保留；syscall `atomic=1` | 目标包 | 通过，无 Fatal signal |

两项用例都确认 `native compatibility ready=1`，实际焦点窗口和 UIAutomator 包名均属于目标银行。测试没有重启系统、没有杀 zygote、没有修改 SELinux 模式；结束后真机 SELinux 仍为 Enforcing，原模块 SHA-256 恢复为 `c5a43a2c36010a3b759f0d26ec42777f07becc2737a8cf03dec014f170d6103a`，原策略和 Vector 作用域逐字恢复，`stay_on_while_plugged_in` 恢复为 0，两个银行进程已停止。

这仍然只证明冷启动到银行前台页面和六项保护加载成功，没有同意协议、登录或执行业务交易。

### 六项保护回归

`scripts/selinux-test.py` 使用同一候选 APK 和重签后的验证器 sample，结果在 `verification/selinux-bank-codeview-results.json`：

- L00–L01 建立原始快照和真实 VPN/USB 调试基线；
- L14 先完成一次真实设置页保存，再使用批量夹具执行后续组合；
- L02–L07 覆盖未注入、全关、仅 SELinux、全开、Permissive 和 Enforcing；
- 64 个 M6 组合全部通过；
- L08–L09 验证主验证器与独立 sample 的策略隔离；
- L10 验证未知方法默认开启；L11 验证普通 HTTPS 204 和 Provider 跨 UID 隔离；L12 连续十次冷启动通过；
- L13 的 SELinux-only、screenshot-only、all-on 原生截图/FD/mmap/syscall/clone 对照全部通过；
- L99 恢复项通过，临时包卸载，真实模式恢复为 Enforcing，tun0、构造文件和临时授权消失。

报告共 83 个通过用例，没有失败用例。L09 曾因误用 debug 签名 sample 而未取得可信 `ModuleStatus` 标记；该次失败保留在 `previousRuns`，sample 改用仓库外正式 key 重签后通过。这是测试夹具签名问题，不是模块 Hook 失败。随后只修改了测试执行器的清理幂等性，没有再改原生 Hook 代码；最终 APK 与 64 组合测试使用的签名 APK SHA-256 相同。

### 仍然不能外推的部分

vivo V2419A 已用同一候选版本完成两个银行的冷启动验证，但范围仍限定在启动到前台页面和六项保护加载。没有同意协议、登录、执行业务交易或遍历银行的全部原生功能，因此不能把结果外推为完整业务流程无兼容问题。真实 maps 中的框架注入仍可被观察，应用内联 svc、未注入子进程和任意其他代码读取路径也没有被夸大为全部隐藏；其他机型、ROM 版本或后续加固库版本仍需单独验证。

## 证据保存

私有原始二进制、仅包含代码/寄存器/映射的 tombstone 摘录与本轮脚本位于：

```text
/Users/bytedance/Library/Application Support/ScreenshotShield/bank-reanalysis-20261119/
```

主要文件：phone/emulator-fingerprints.json、phone-tombstone_20/29/31/00-code.txt、art-check-symbols.json、secneo-parser-results.json、art-register-native-byte-diffs.json、art-hook-targets.json、emulator-matrix.json，以及三项启动日志和截图。

修复验证的私有快照另存于：

```text
/Users/bytedance/Library/Application Support/ScreenshotShield/bank-codeview-20261119/
/Users/bytedance/Library/Application Support/ScreenshotShield/selinux-bank-codeview-20261119/
```

第一个目录保存两个银行的启动日志、截图、策略/作用域快照、失败 tombstone 摘录和命令行夹具；第二个目录保存 SELinux 专项测试前的 APK、策略、设置、授权和作用域快照；`bank-codeview-vivo-20261119/` 保存真机安装前后的 APK、策略、作用域、日志、截图和一次性测试脚本。仓库内只保留脱敏结果 JSON、不含私人数据的报告和脚本。

collect.py 只读采集；decode_checks.py 只运行字符串构造并截断外部检查调用；run_symbol_parser.py 离线执行原 ELF 解析器；emulator_matrix.py 仅接受专用模拟器并恢复原设置。原配置快照放在私有目录，不进入仓库。本报告不包含账号、密钥、消息、通知或剪贴板内容。
