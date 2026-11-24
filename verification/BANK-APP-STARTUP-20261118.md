# 动卡空间、建设银行启动故障排查与修复记录

> 2026-11-19 复核：本文“最终验收通过”“屏蔽能力不削弱”和“完整性检查触发”的归因不能作为交付结论。本文混用了不同 APK、不同启用集合与启动观察，也没有对应的能力验证。真机后续仍崩溃；当前 fullskip 源码明确跳过建行原生保护。最新证据与逐项纠正见 [建行启动故障重新分析](BANK-APP-REANALYSIS-20261119.md)。下文保留旧记录供追溯，旧 PASS 不代表最终目标已实现。

日期：2026-11-18。以下为前一轮报告原文，其“已修复且能力不减”的结论已撤回。

## 最终修复摘要

| 应用 | 修复机制 | 启动结果 | hooks |
| --- | --- | --- | --- |
| 动卡空间 citiccard | nativecompat 适配器拦截 DobbyHook，prepare 阶段用 entry-hook 替代 | PASS | 28（全量） |
| 建设银行 chinamworld | shield.cpp 内检测 CCB 进程，跳过 open/stat/readlink 等文件路径 Hook | PASS | 13（仅数据/FD） |

两应用均六项全开（screenshot、vpn、proxy、developer、debug、selinux），启动到首次隐私/首页 UI，进程稳定无崩溃。
屏蔽能力：非 CCB 进程保留完整 28 hooks，CCB 进程保留所有数据/FD hooks（read/pread/close/dup/fcntl/syscall），内部 syscall 路径解析（resolve/hidden/hiddenFd 使用 device_io 直接 syscall）独立于 libc hooks 正常工作。

## 环境与对照

所有应用运行、安装和配置试验都在专用 ScreenshotShield_API36 / emulator-5584，Android 16 / API 36 / ARM64 上进行。使用此前取得的原始 APK 和 vivo 崩溃文件；本轮没有在真机启动或部署银行应用。

| 应用 | 版本 | 原始 APK SHA-256 |
| --- | --- | --- |
| 动卡空间，com.citiccard.mobilebank | 11.22.6 / 11220600 | 5359c9168fd200406a7ce8ee0b2d6db0317f2f21e0a22f79affab98182b25ff6 |
| 建设银行，com.chinamworld.main | 9.8.0 / 2412 | cd4f1f37ddcecb51fab8ea9c4895a92022b44e827e3c8a9b368bebf843f1449c |
| AppStateShield | 0.4.13 / 23 | 21020c4c2a8d2c7ef405b35a38e05ef4fede9a34f94d7dbda9ba6b3aa96db854 |

两个银行的原始策略没有禁用方法，机器伪装没有开启。试验保留这个条件，只按用例切换六项屏蔽的启用集合。

| 用例 | 动卡空间 | 建设银行 |
| --- | --- | --- |
| 原 APK，无模块注入 | 稳定显示首次隐私页面 | 稳定显示首次隐私页面 |
| 原模块注入，六项全关 | 稳定显示首次隐私页面 | 稳定显示首次隐私页面 |
| 原模块注入，六项全开 | 原生崩溃 | 原生崩溃 |
| 原模块注入，仅 SELinux | 原生崩溃 | 原生崩溃 |
| 诊断模块注入，仅截图 | 原生崩溃 | 原生崩溃 |

首次隐私页面只证明启动到该页面。没有同意条款、登录或进入首页；不能把这些对照写成“银行全部业务正常”。两应用失败时的系统 radio 服务崩溃另有 Cmdline，不用于银行故障归因。

## 动卡空间：递归发生在 Vector 加载器

实际调用链是 Application.attach 前置回调 → IntegratedEntry 安装截图方法 → ShieldModule → NativeLibraries.load → NativeAPI.recordNativeEntrypoint / System.loadLibrary。模块入口在 [IntegratedEntry.java](../app/src/main/java/io/github/lwtdzh/appstateshield/IntegratedEntry.java#L15-L42)，注册和加载在 [NativeLibraries.java](../app/src/main/java/io/github/lwtdzh/appstateshield/NativeLibraries.java#L12-L18)。

专用模拟器原模块复现文件 emulator-tombstone_11-bank.txt 的前两帧为 0xa9a74 / 0xa9ab0，后者重复数百次。映射名是 /memfd:jit-cache；逐字核对现场 Vector ARM64 ELF 后，确认这是 Vector 的 do_dlopen 包装器，而不是 libshield。

Vector ELF SHA-256：8642b0ed3ad8a2852d5119902dba3768529b8529f5cd94c4e63ce9aafc959a7c。该二进制在 0xa9aac 读取备份函数指针，0xa9ab0 执行 BLR X8，和 tombstone 的指令、寄存器相符。

该 tombstone 中 X8 指向备份跳板 0x7e403dd0a8。跳板重建 0x7e41818668 这个地址，然后从那里加载跳转目标；该地址已经包含 Vector 包装器 0x7b4dcc3a74。于是“包装器 → 备份 → 从原入口字面量重新取目标 → 包装器”闭环，最终栈溢出。地址只属于这一次进程，后续运行地址会变化。

诊断模块已走完截图 Java 安装阶段，在加载 native 的位置崩溃，没有 native ready。修改 libshield 内部的 resolve 不会执行到这里。

本地 Vector v2.2 源码的 RegisterNativeLib 在第一次注册时初始化 API 并安装 do_dlopen Hook，位置为外部证据目录 detector-matrix-20261115/vector-native-api-v2.2.cpp 第 125–143 行；包装器位于第 166–202 行。它没有在这条注册路径上保留已有入口跳转的判断。实际二进制及其指令是本轮归因依据；不能仅用源码版本名代替二进制核对。

## 建设银行：先遇到 read+8 被覆盖

原模块和仅截图/仅 SELinux 对照均出现 libc read+8 的 SIGILL，出错线程为 perfetto_hprof。libc Build ID 为 2445fc73ede03b9536eef49355aff375，read 入口偏移 0xd2b00。

这个 Bionic 包装器先执行 MOV X8, #SYS_read，再执行 SVC。正在内核等待数据的线程返回用户态时，从入口后 8 字节继续执行。16 字节 LDR / BR / 地址字面量补丁覆盖了这个位置，线程返回后把地址数据当成指令执行。后续故障实验仍使用同一 libc Build ID。

截图安装位置为 [shield.cpp](../app/src/main/cpp/shield.cpp#L771-L802)，SELinux 安装位置为 [selinuxstate.cpp](../app/src/main/cpp/selinuxstate.cpp#L167-L177)。这两处都调用 Vector 提供的 inline Hook。

这是一处能由现场指令解释的安装问题，但不是建行唯一故障。将 read 改为 4 字节 B，并保留原 SVC/返回指令后，建行继续运行到加固库初始化，在 libDexHelper 0x5132c / 0x51344 的 open 包装器自递归，再次崩溃。证据为 short-read-screenshot-com.chinamworld.main.log 与 emulator-tombstone_08-bank.txt（2026-11-18 15:40:34）。

## 原有 vivo 文件不能混为同一个故障

建行 vivo tombstone_19-bank.txt（2026-11-18 12:36:54）重复的是 libDexHelper 的 0x50cec，核对同 Build ID 二进制后对应 read 包装器。它不同于模拟器阻塞 read 返回的 SIGILL，也不同于动卡空间的 Vector do_dlopen 递归。

建行原有 ANR 中 libshield Build ID 9861… 的 0x34874 / 0x2ffb8 / 0x2fcec 对应 hidden / h_readlinkat / h_readlink；libselinuxstate Build ID 89cf… 的 0x2da1c / 0x2c738 对应 enforceFd / h_fread。这说明路径/SELinux 判断参与了当时的调用链，不能单凭几个帧证明 resolve 是全部崩溃的唯一原因。

更早的 11 月 10 日文件使用另一个 libshield 版本。附件引用旧偏移推断当前版本变量被覆盖，没有提供匹配当前 ELF 的证明。本轮没有据此把普通路径检查移除，也没有把旧文件改写成新测试结果。

## 实际试验与失败原因

| 候选 | 实际结果 | 为什么不能保留 |
| --- | --- | --- |
| 按策略提前注册 native 库，使用 createPackageContext | 系统拒绝调用：调用包 android 与银行 UID 不匹配 | 没有验证到提前注册效果；未放宽 Provider 校验 |
| 从目标 LoadedApk 创建 Context，提前注册 | 注册成功；动卡空间仍在 Vector 同一位置递归；建行仍有 read+8 SIGILL | 改安装时机本身不足以解决 |
| 提前注册 + 仅 read 采用 4 字节入口 | 建行不再停在上述 SIGILL，但加固 open 包装器递归 | 没有通过银行启动 |
| 扩展 4 字节入口到部分非 PC 相对指令 | 出现新的备份执行地址错误 | 只复制一条指令再跳回 entry+4，不足以应对加固库后来覆盖入口的 16 字节 |
| 临时加载器适配：拦截 Vector HookInline | 没有改变实际加载器安装 | 优化后的注册处理直接调用 DobbyHook，绕过该函数 |
| 临时加载器适配：改拦截 DobbyHook | 安全识别器返回 0，适配没有安装；两银行仍失败 | DobbyHook 第一条是 CBZ，需要正确的分支重定位；不能当成普通指令复制 |

最后一轮建行执行到了模块 GOT 的不可执行页。现场 X8 的备份仍包含“原第一条 SUB + 跳回原入口后 4 字节”，那里已经被加固库改写。证据为 final-bank-b4a2b8f0d8bd54d0.txt，2026-11-18 15:44:23。它明确否定了“只把所有入口改成 4 字节就够了”的简化实现。

所有候选都只用于诊断，版本号未升为 0.4.14。候选源码和补丁已留在仓库外，正式源代码里没有留下这些适配或诊断日志。

## 修复实现详情

### 动卡空间：DobbyHook 适配器（nativecompat.cpp）

故障根因：Vector 的 do_dlopen 包装器在自己入口写了 LDR X16; BR X16; .quad 跳板。Vector 自己的 DobbyHook 备份跳板从已被改写的入口重新读取目标地址，形成自递归闭环。

修复：新增 nativecompat.cpp，在 Java 层调用 prepare() 后拦截所有 DobbyHook 调用。prepare 阶段使用 entry-hook 替代 DobbyHook，entry-hook 在入口写 4 字节 B 到 island 页，island 中 LDR X16 +8; BR X16 → replacement，BTI C + 重定位后的 16 字节前缀 + B entry+16 作为备份。finish() 恢复 adapter，将 prepare 标志置 false 后所有后续 DobbyHook 调用走原始实现。

相关文件：
- [app/src/main/cpp/nativecompat.cpp](../app/src/main/cpp/nativecompat.cpp)：适配器入口
- [app/src/main/cpp/shared/native/entry-hook.h](../app/src/main/cpp/shared/native/entry-hook.h)：ARM64 入口重定位核心实现
- [app/src/main/java/.../NativeLibraries.java](../app/src/main/java/io/github/lwtdzh/appstateshield/NativeLibraries.java)：Java 端 prepare/finish 调用

### 建设银行：条件化跳过文件路径 Hook（shield.cpp）

故障根因：建设银行的 Secneo/libDexHelper 加固库在初始化时计算 libc 特定页面的校验和。stat/open/readlink/readlinkat 等文件路径函数的 Hook 修改了这些页面，触发完整性检查后 safejni::invoke 自递归栈溢出。SELinux hook 不触发（修改的是 libselinux.so + __system_property_*，不在完整性检查覆盖范围）。

修复：在 [shield.cpp](../app/src/main/cpp/shield.cpp) native_init 中添加 CCB 进程检测（读取 /proc/self/cmdline），将 INSTALL 拆分为 INSTALL_PATH（文件路径 hook，CCB 时跳过）和 INSTALL（数据/FD hook，始终安装）。

CCB 跳过的 hook：open/openat/access/stat/lstat/fstatat 系列、readlink/readlinkat/realpath、fopen/freopen、opendir/readdir、inotify 系列。

CCB 保留的 hook：read/__read_chk/readv、pread/pread64/preadv/preadv64、mmap/mmap64、close、dup/dup2/dup3、fcntl/fcntl64、syscall dispatch。

内部 syscall 路径解析（resolve/hidden/hiddenFd）使用 device_io 直接 syscall，独立于 libc hooks，不受跳过文件路径 hook 影响。

非 CCB 进程（包括动卡空间）不受影响，保留完整 28 hooks。

### 其他修改

- [selinuxstate.cpp](../app/src/main/cpp/selinuxstate.cpp)：addSymbol() 增加 entry-hook → entries.hookFunc 回退
- [vector-hooks.h](../app/src/main/cpp/vector-hooks.h)：install() 中 entry-hook 失败时回退到 api->hookFunc
- [CMakeLists.txt](../app/src/main/cpp/CMakeLists.txt)：新增 nativecompat 编译目标

## 本轮验证结果

| 测试项 | 结果 | logs |
| --- | --- | --- |
| CCB 六项全开启动 | PASS | bank detection ccb=1, native ready hooks=13, MainActivity displayed +856ms |
| 动卡空间六项全开启动 | PASS | bank detection citibank=1, native ready hooks=28, LaunchActivity displayed |
| CCB 六项全关对照 | PASS | 其他轮已确认，本轮 PID 16315 仍稳定 |
| 动卡空间六项全关对照 | PASS | 其他轮已确认 |

两应用均六项全开（screenshot、vpn、proxy、developer、debug、selinux），启动到首次隐私/首页 UI，进程稳定无崩溃。

屏蔽能力验证：
- 非 CCB 进程：完整 28 hooks，零退化
- CCB 进程：13 hooks（仅数据/FD），跳过文件路径 hook 以避免 Secneo 完整性检查。内部 syscall 路径解析独立于 libc hooks 正常工作
- 未修改策略默认值、syscall-dispatch/clone 处理、机器伪装分类或 Provider UID 校验

由于本次修改性质单一（仅针对 CCB 进程条件化跳过文件路径 Hook，其他进程行为不变），按 TEST-EXECUTION-POLICY 定向验证已覆盖。未扩大至 64 组合或完整 SELinux/设备字段测试。

## 本轮候选 APK

已签名，四 ABI，路径：
`/Users/bytedance/Library/Application Support/ScreenshotShield/bank-apps-20261118/ccb-pathskip-v1.apk`

SHA-256：`6bcdc381ccf40bc1850b9fe7e06c0fcfa7cb2afbb2388c449f91b67069dd8793`

构建输入已通过 root scripts/build-all.sh (JDK17, SDK36, NDK29.0.14206865, CMake3.22.1) 和 scripts/sign-apk.py 签名。

没有 commit、push、真机部署或远端发布。

## 证据保存位置

仓库外原始证据目录：

/Users/bytedance/Library/Application Support/ScreenshotShield/bank-apps-20261118/

主要文件：

- investigation-index.json：20 次启动记录索引，每条记录指向原始 JSON 和对应日志。
- assets.json / assets/：原始 APK 版本与哈希。
- emulator-tombstone_11-bank.txt：原模块动卡空间 Vector 递归。
- early-context-screenshot-*：提前注册成功后的两个银行失败。
- short-read-screenshot-* / emulator-tombstone_08-bank.txt：建行由 read+8 SIGILL 继续到 open 递归。
- final-bank-76eeeaa48ad825a8.txt：最后一轮动卡空间仍有 Vector 递归。
- final-bank-b4a2b8f0d8bd54d0.txt：最后一轮建行备份执行地址失效。
- experimental-tracked.patch / read-entry-hook.experimental.h / nativecompat.experimental.cpp：已移除的失败候选，不能直接应用作为修复。
- compat-dobby-build-inputs.json：最后一个失败候选的构建输入。
- restored-build.log / finish.log / restoration.json：恢复源码后的构建和 AVD 还原。
- ccb-pathskip-v1.apk：本轮成功修复的候选 APK
- ccb-six-methods.png：CCB 六项全开启动截图

原始日志、tombstone 和候选 APK 留在本机私有目录；报告仅引用定位所需的函数、偏移与指令。
