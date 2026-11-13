# 应用状态屏蔽 · AppStateShield

一个 Vector 模块，按应用屏蔽截图、VPN、网络代理、开发者选项、USB/无线调试及 SELinux 状态。当前版本为 **0.3.1**，模块和验证器一起升级。保留一个“应用状态验证器”，用来观察应用实际读取结果。

主模块默认不显示桌面图标。从 Vector 的模块页打开设置，开启“显示应用图标”后也可从桌面进入，并供分身工具识别。能否分身仍取决于工具支持。图标开关按 Android 用户保存，升级后保留选择。Vector 决定作用域；设置页为作用域内的应用选择屏蔽方法。未定制应用默认全部开启，包括以后新增的方法。

验证器首页增加状态信息条，每 2 秒刷新 VPN、网络代理、开发者选项、USB/无线调试和 SELinux。它展示本应用读到的值；注入模块后，读数可能经过屏蔽。读取失败显示“无法读取”。传统日志、读取检查和来源选择继续保留。

图标、状态条和 vivo 安装的实际结果见 [0.3.1 测试记录](verification/STATUS-UI-0.3.1.md)。SELinux 文件不可读且 Java API 返回 false 时显示“模式无法确认”，避免把读取失败当成宽容模式。

“本次打开”的截图次数与日志的信号条数分别统计：按文件路径、图片 ID 和 2 秒内的多入口信号合并估算；快速连拍、延迟通知或没有身份的信号仍可能误差。仅检测首页前台期间计数，旋转、返回、清空日志和重启监听保留次数；结束页面重新打开或冷启动后清零。0 次需要结合权限和真实截图基线判断。

## 使用

1. 安装 AppStateShield APK，在 Vector 启用模块并选择作用域。
2. 默认即可使用。需要单独设置时，从 Vector 打开模块设置，点“添加应用”，选择应用，调整开关并保存。
3. 强行停止并重新打开目标应用，让新配置生效。
4. 删除定制条目恢复全部开启。定制列表不改变 Vector 作用域。

六个开关独立生效。SELinux 开启时，目标应用的 Java API、libselinux 状态函数和常见 enforce 文件读取返回强制执行状态（Enforcing / 1）；系统实际模式保持原样。关闭后恢复真实读取。旧定制只保存已关闭的方法，升级后 SELinux 默认开启。

SELinux 不修改系统权限或进程安全上下文。直接内核系统调用、未注入的 shell 子进程、其他挂载位置及保留的加固入口仍可能读到真实模式；读取原本失败时不会伪造文件成功。具体路径见[SELinux 验证记录](verification/SELINUX-0.3.0.md)。其他应用的自定义、内核或服务端检测也不保证全部覆盖。

0.2.1 修复了 vivo 上动卡空间开启截图屏蔽后启动卡住的问题。ARM64 原生层会保留函数入口已有的外部跳转，避免覆盖应用加固库的 Hook。这些入口的原生读取无法由本模块完整屏蔽；Java 层和其余成功安装的原生 Hook 继续生效。验证范围和限制见[兼容性记录](verification/VIVO-COMPATIBILITY-0.2.1.md)。

## 工程

```text
app/             整合模块、设置页、策略服务及四组 native hooks
verifier/        保留验证器、截图日志、低层文件读取和设备状态检查
scripts/         根工程构建、签名、专用模拟器与测试执行
docs/            整合设计、逐步人工测试手册
verification/    当前验证报告与 legacy 历史记录
gradle/          全工程共用 wrapper
```

`:app` 包名为 `io.github.lwtdzh.appstateshield`。`:verifier` 保留 `io.github.lwtdzh.screenshotdetector` 和原签名。sampleA/sampleB flavors 只供多应用隔离测试，正式交付不需要安装。

## 构建

JDK17、Android SDK36、NDK29.0.14206865、CMake3.22.1：

```sh
./scripts/build-all.sh
python3 scripts/sign-apk.py app/build/outputs/apk/release/app-release-unsigned.apk /path/to/AppStateShield.apk
python3 scripts/sign-apk.py verifier/build/outputs/apk/primary/release/verifier-primary-release-unsigned.apk /path/to/AppStateVerifier.apk
```

主模块 minSdk27/targetSdk36。验证器 minSdk28/targetSdk28，保留旧文件权限以比较 JNI/NIO 读取；这是侧载的诊断应用，未面向 Play 发布。官方截图日志页要求 API34，较低版本打开设备状态检查。

## 验证与迁移

[人工测试手册](docs/TEST-MANUAL.md) 包含设置页操作、64 种开关组合、多应用隔离、早期启动读取、SELinux 真实模式对照、SystemUI 截图、选图授权、联网及清理步骤。[整合设计](docs/ARCHITECTURE.md) 说明配置和 Hook 安装；[工程关系](PROJECT-RELATIONSHIPS.md) 记录迁移。

整合模块使用新包名，可与旧模块共存。迁移时先禁用旧 ScreenshotShield、VPNStateShield、DeveloperStateShield 对同一应用的作用域，避免重复 Hook，再把相同目标加入新模块。旧模块没有按应用开关可迁移，整合版默认全部开启。验证器以原包名同签名升级。

历史验证记录保存在 `verification/legacy/`；历史脚本在 `scripts/legacy/` 仅供查阅，不应用于新布局或恢复旧模块。
