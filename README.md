# 应用状态屏蔽 · AppStateShield

一个 Vector 模块，按应用屏蔽截图、VPN、网络代理、开发者选项及 USB/无线调试状态。当前模块版本为 **0.2.1**，验证器保留 **0.2.0**。保留一个“应用状态验证器”，用来观察系统实际读取结果。

主模块没有桌面图标。从 Vector 的模块页打开设置。Vector 决定作用域；设置页为作用域内的应用选择屏蔽方法。未定制应用默认全部开启，包括以后新增的方法。

## 使用

1. 安装 AppStateShield APK，在 Vector 启用模块并选择作用域。
2. 默认即可使用。需要单独设置时，从 Vector 打开模块设置，点“添加应用”，选择应用，调整开关并保存。
3. 强行停止并重新打开目标应用，让新配置生效。
4. 删除定制条目恢复全部开启。定制列表不改变 Vector 作用域。

截图、VPN、代理、开发者选项、USB/无线调试是五个独立开关。系统实际功能继续运行，目标应用读到的状态按所选方法处理。SELinux 尚未实现，设置中标注“待开发”。没有一种 API 屏蔽能保证覆盖任意应用的自定义、内核或服务端检测；具体读取路径和真实设备结果见测试记录。

0.2.1 修复了 vivo 上动卡空间开启截图屏蔽后启动卡住的问题。ARM64 原生层会保留函数入口已有的外部跳转，避免覆盖应用加固库的 Hook。这些入口的原生读取无法由本模块完整屏蔽；Java 层和其余成功安装的原生 Hook 继续生效。验证范围和限制见[兼容性记录](verification/VIVO-COMPATIBILITY-0.2.1.md)。

## 工程

```text
app/             整合模块、设置页、策略服务及三组 native hooks
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

[人工测试手册](docs/TEST-MANUAL.md) 包含设置页操作、32 种开关组合、多应用隔离、早期启动读取、真实 SystemUI 截图、选图授权、联网及清理步骤。[整合设计](docs/ARCHITECTURE.md) 说明配置和 Hook 安装；[工程关系](PROJECT-RELATIONSHIPS.md) 记录迁移。

整合模块使用新包名，可与旧模块共存。迁移时先禁用旧 ScreenshotShield、VPNStateShield、DeveloperStateShield 对同一应用的作用域，避免重复 Hook，再把相同目标加入新模块。旧模块没有按应用开关可迁移，整合版默认全部开启。验证器以原包名同签名升级。

历史验证记录保存在 `verification/legacy/`；历史脚本在 `scripts/legacy/` 仅供查阅，不应用于新布局或恢复旧模块。
