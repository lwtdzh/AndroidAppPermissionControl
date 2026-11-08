# 阻止软件检测截图 · ScreenshotShield

一个由 Vector 加载的 Xposed 模块。所有拦截默认开启，模块没有应用列表、白名单、黑名单或独立开关；应用范围完全由 Vector 的作用域决定。

这是独立的 Android 项目，Gradle 名称为 `ScreenshotShield`，源码在本目录的 `app/` 中。通用开发目标与 Agent 说明见 [集合 README](../README.md)、[AGENTS.md](../AGENTS.md) 和[共享工作流 Skill](../.trae/skills/android-permission-workflow/SKILL.md)。

三个项目的关系、共用测试条件和执行顺序统一记录在 [PROJECT-RELATIONSHIPS.md](../PROJECT-RELATIONSHIPS.md)。修改本项目时请同时检查受影响的检测软件与 Probe 测试。

带界面日志的检测软件在独立项目 [module-screenshot-detector](../module-screenshot-detector/README.md)，自动化验证 App 与模拟器脚本在 [module-screenshot-probe](../module-screenshot-probe/README.md)。本模块的审查与验证记录保存在 `COVERAGE-AUDIT.md` 和 `verification/`。

## 安装

1. 安装提供的 `ScreenshotShield-0.1.3.apk`。
2. 在 Vector 中启用“阻止软件检测截图”，勾选需要保护的应用。
3. 结束并重新打开这些应用。修改作用域后，也需要重新启动目标应用进程。

模块不显示桌面图标；从 Vector/Xposed 的模块设置入口可以打开使用说明。独立的“截图检测日志”App 保留桌面图标。系统截图继续保存，选中应用的截图检测会受到拦截。

## 界面语言

应用名称、模块说明和界面全文支持简体中文、英文、日文，以及繁体中文的通用、台湾、香港、澳门版本，默认跟随系统语言。简体名称为“阻止软件检测截图”，台湾繁体为“阻止軟體偵測截圖”，香港和澳门繁体为“阻止軟件偵測截圖”。

Android 13 及以上也可在系统的“应用语言”设置中单独选择本应用的语言。较早的 Android 版本跟随系统语言。长文本页面可以滚动查看。

## 截图检测日志 App

独立安装包 `ScreenshotDetector-0.1.1.apk` 用于手动测试，应用名称为“截图检测日志”（英文系统显示 `Screenshot Detection Log`），包名为 `io.github.lwtdzh.screenshotdetector`，需要 Android 14 或以上。

打开后默认同时监听 18 个入口，也可以在下拉列表里单独选择。日志注明时间和来源；计数表示截图信号条数，一次截图可以产生多条信号。每个入口分别显示正在监听、需要权限或不可用。照片、文件、通知和无障碍的授权按钮会打开对应的系统权限页面。

检测入口包括官方 API、直接 Binder、MediaStore 变化通知和三种独立查询、Java 文件监听及元数据轮询、native inotify / libc / syscall、动态与静态广播、剪贴板图片描述和 URI、通知回调与列表、无障碍事件与节点/窗口。原有图片和通知先作为基线，不算新截图；自动监听不分析图片像素。

“选择图片检查读取”通过系统选图器获得真实 URI 授权，再逐项检查文档 ID、文件名、输入流、asset、client、文件描述符和缩略图，并测试 native fd 的读取与元数据入口。这些结果单列为读取检查，不计入新截图。文件名、路径、URI、通知正文和其他界面文本均不会出现在日志里。

建议先让检测 App 保持在模块作用域之外，确认同一种操作在哪些入口产生信号。再将它加入 Vector 作用域，强行停止并重新打开，重复操作。没有权限、系统不支持、ROM 未发送对应广播/通知时，零日志不能证明拦截成功。详细步骤和已测入口见 [检测软件使用与验证](../module-screenshot-detector/README.md)。

日志 App 保留桌面入口，支持简体、英文、日文和繁体各地区；它不会自行更改 Vector 配置。切换到其他应用时暂停记录，最多保留最近 200 条。通知和无障碍服务只有用户开启后才连接；退出检测页面后不记录它们传来的事件。

## 实现

| 路径 | 处理方式 |
| --- | --- |
| Android 14+ 官方截图回调 | 拦截 Activity、回调控制器和 ActivityTaskManager Binder 代理；直接 BinderProxy.transact 调用根据当前系统生成的 transaction 字段及接口名拦截 |
| MediaStore 查询 | 在 provider 执行前追加截图排除条件，覆盖旧式 selection、Bundle、ContentProviderClient 和 Binder 代理；只查询 `_id` 的调用也会过滤 |
| 文档提供者和旧式缩略图 | 按文件名、路径、document ID 过滤 cursor；处理 MediaDocuments 的 image ID 映射和缩略图的 image_id。需要时增加识别列，过滤后只向调用者返回原投影 |
| 相册变化通知 | 注册时记录媒体 observer，分发时过滤截图 item URI；混合 URI 数组只保留可见项 |
| 无 item 身份的媒体通知 | 媒体 observer 收到集合/null 通知时抑制通知；普通图片的查询结果仍保留 |
| 内容读取 | 阻止打开已识别的截图内容、文件描述符、asset、缩略图，包括 client 与 Binder 代理入口 |
| Java 文件访问 | 隐藏共享存储中的截图文件元数据、目录列表及 FileInputStream/RandomAccessFile 读取 |
| native 文件访问 | libc open/openat、fortify 入口、access/faccessat、stat 家族、stdio、目录枚举、readlink/realpath；解析相对路径、符号链接、`/proc/.../fd` 和 `/proc/.../root` 别名 |
| 已打开的文件描述符 | 在 read/readv、pread/preadv、fstat、mmap 等入口重新识别 fd 所指向的文件；inotify 的 dup/fcntl 副本共享 watch 状态 |
| Java FileObserver 与 native inotify | 阻止直接监听截图目录；监听普通父目录时过滤截图事件，保留普通文件事件 |
| libc syscall | 过滤 openat、faccessat、newfstatat/statx、getdents64 与 inotify/read 的已实现入口 |
| 截图广播 | 抑制动作末段含截图标识的动态、静态广播；覆盖 Args.run/getRunnable 和 ActivityThread.handleReceiver；注册时补充拦截具体 receiver 的 onReceive，保留框架的 PendingResult 完成流程 |
| 剪贴板 | 隐藏带截图标识的图片 ClipDescription、截图 URI，以及可识别的剪贴板变化通知；普通文本保留 |
| 通知读取 | 动态拦截通知监听服务的具体回调；过滤 active/snoozed 列表和已识别的 ranking key，保留框架自身的 ranking 更新 |
| 无障碍信息 | 动态拦截服务的具体回调；过滤可识别的截图事件、窗口、根节点、焦点和 AccessibilityInteractionClient 查询结果 |

截图识别使用文件名和目录中的 `Screenshot`、`Screen_shot`、`Screencap`、`Screen_capture`、截图、截屏等常见标识。文件路径过滤限定在共享存储；不会因为应用包名包含 screenshot 就屏蔽它自己的 APK 或私有文件。

native 代码使用 Vector 的公开 `native_init` ABI 和框架提供的 inline hook。读取 libc 内存中的 ELF 符号长度后，跳过小于 16 字节的入口，避免覆盖相邻函数。短包装入口通过其底层函数处理，例如 `inotify_init` 通过 `inotify_init1` 和 `inotify_add_watch` 处理。初始化期间直接使用已经加载的 libc，不再次调用 dlopen。

## 使用效果与限制

选中的应用看不到已识别的已有或新增截图，因此其相册选择、上传截图、读取截图等功能也会受影响。直接写入截图的只写文件句柄保留，读写模式可能受到拦截。集合/null 相册通知缺少具体图片身份，屏蔽这类通知也可能延迟目标应用刷新普通图片。

这套规则不承诺覆盖任何应用的所有私有实现。重命名并移动到普通目录的截图可能失去可识别标记；自定义 ROM 的私有 Binder 协议、任意手写的原始 ContentProvider Parcel、直接内联汇编执行系统调用、具有 root/系统权限的辅助进程、未注入的外部程序，以及应用自己的内部事件需要逐一分析。目录时间、存储总量、窗口变化、声音和 inotify 的 poll/epoll 就绪状态还可能用于推测截图。普通截图、屏幕录制、FLAG_SECURE 禁止截图属于不同事件，本版本专门处理截图检测。

识别只使用文件名、路径、URI、列值和系统界面元数据，不扫描图片像素或做内容识别。通知和无障碍过滤限定于 Android/SystemUI 和可识别的截图组件；遇到没有可识别标识的厂商实现，需要结合实际日志补规则。详情见 [截图检测调查与防护记录](COVERAGE-AUDIT.md)。

Android 最低安装版本为 8.1，构建使用 SDK 36，包含 ARM64、ARM32、x86_64、x86 native 库。运行时验证情况见随安装包提供的测试记录；编译成功不代表所有架构和 ROM 已实测。

## 构建

需要 JDK 17、Android SDK 36、NDK `29.0.14206865` 和 CMake `3.22.1`。

```sh
export JAVA_HOME=/path/to/jdk17
export ANDROID_HOME=/path/to/android-sdk
./gradlew :app:assembleRelease
```

`app/` 是本项目唯一的 Android 子模块，APK 输出到 `app/build/outputs/apk/`。可以直接在 Android Studio 中打开本目录。两个测试 App 各自使用独立项目的 Gradle wrapper，不会被打进本模块 APK。共享签名脚本为 `../scripts/sign-apk.py`。

## 模拟器验证

脚本只接受 `emulator-*`，不会把测试写入真机。模拟器需要已经安装 Magisk/Zygisk 和 Vector 2.2，并拥有 root ADB。

本机已配置专用 `ScreenshotShield_API36`，端口为 `5584`。AVD 数据和修补后的 ramdisk 保存在 `~/Library/Application Support/ScreenshotShield/emulator/`，与其他模拟器分开保存。

```sh
../module-screenshot-probe/scripts/start-emulator.sh -no-window
adb -s emulator-5584 root
adb -s emulator-5584 shell /debug_ramdisk/su -c id
adb -s emulator-5584 shell /data/adb/modules/zygisk_vector/cli --json status
```

启动脚本前台运行；省略 `-no-window` 可打开模拟器窗口。APK 的签名密钥保存在同一状态目录的 `signing/` 子目录，权限为本地用户私有，未包含在源码中。

```sh
../module-screenshot-probe/gradlew -p ../module-screenshot-probe :app:assembleDebug
python3 ../module-screenshot-probe/scripts/emulator-test.py --serial emulator-5584 \
  --module-apk /path/to/ScreenshotShield-0.1.3.apk --output /tmp/integration.json
python3 ../module-screenshot-probe/scripts/official-callback-test.py \
  --serial emulator-5584 --output /tmp/official.json
python3 ../module-screenshot-detector/scripts/detector-test.py
```

若模拟器中已经安装签名 release 包，给第一个脚本追加 `--module-apk /path/to/ScreenshotShield-0.1.3.apk`。不同签名的 debug/release 包不能直接相互覆盖安装。

第一个脚本依次测试模块关闭、模块开启且作用域包含测试 App、模块开启但作用域排除测试 App。它从独立进程写入文件、通过真实 provider 触发通知，并检查普通文件没有一起被隐藏。

文档测试从系统文件选择器实际选择夹具、取得 URI 授权后执行，检查只请求 `document_id` 时的行数、列数和内容打开。夹具先通过 MediaProvider 完成索引，避免将选择器不显示空元数据文件误认为模块效果。

native 检查包括 libc 与 syscall 的文件打开、相对 openat、stdio、元数据、getdents64 目录枚举，以及“先 fcntl 复制再添加 watch、关闭原 fd 后从副本读取”的 inotify 场景。ARM64 测试代码用直接内核 open 获得文件描述符，以模拟来自未注入进程的 fd，再验证 libc 的 read/pread/readv/fstat/mmap 拦截；这个夹具明确展示了内联系统调用本身仍能绕过 libc hook。

通知和无障碍回调使用构造的元数据做前后对照，不能据此声称已经测试所有 ROM 的真实截图通知和截图浮层。剪贴板测试等 App 获得窗口焦点后执行，避免把系统拒绝后台读取当作模块效果。

第二个脚本默认注入 SYSRQ 截图快捷键，走 Android 输入策略和 SystemUI 截图链路。必须同时满足“SystemUI 保存了新截图”“模块关闭时官方 API 和直接 Binder 都收到回调”“模块开启时两条回调均为零”。测试只在发现当前系统的 AIDL transaction 字段时暂时放宽隐藏 API 策略；保护状态的验证使用恢复后的系统默认策略。ADB `screencap` 只用于生成 PNG 文件夹具，不算官方回调验证。这是模拟器验证，没有把注入的按键当作真机物理按键证据。

`--trigger console-chord` 可以测试老式模拟器 console 的电源键和音量减键组合。当前 virtio-input 模拟器没有由该路径触发截图，不能把它记录为成功。

`detector-test.py` 只使用专用 `emulator-5584` 上已安装的两个 release APK，检查 13 个实际截图入口在保护前后的日志和界面计数，并单独验证动态、静态广播夹具。运行前需在该专用 AVD 授予照片、所有文件及通知权限；脚本临时连接无障碍服务，完成后恢复原来的无障碍配置和检测 App 作用域。结果保存到 `/tmp/screenshot-detector-work/detector-expanded.json`。直接 Binder 使用当前系统的 AIDL 常量，全程不修改隐藏 API 策略。

## 官方接口资料

- [Vector 2.2](https://github.com/JingMatrix/Vector/releases/tag/v2.2)
- [Vector native ABI](https://github.com/JingMatrix/Vector/blob/v2.2/native/include/core/native_api.h)
- [Android 截图检测](https://developer.android.com/about/versions/14/features/screenshot-detection)
- [Android 16 广播分发实现](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/android16-release/core/java/android/app/LoadedApk.java)
