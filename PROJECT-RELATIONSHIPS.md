# 工程与能力关系

整合版 0.2.0 将六个独立工程迁入一个根 Gradle 工程，正式构建只交付模块和验证器两个 APK。

| 原工程 | 现位置 | 作用 |
|---|---|---|
| module-screenshot-shield | app/ 内 screenshotshield Java 包、shield native 库 | 截图回调、文件/FD、媒体、广播及其他信号屏蔽 |
| module-vpn-state-shield | app/ 内 vpnstateshield Java 包、vpnstate native 库 | VPN 观察和代理 metadata 两个独立方法 |
| module-developer-state-shield | app/ 内 developerstateshield Java 包、developerstate native 库 | 开发者选项与 USB/无线调试两个独立方法 |
| module-screenshot-detector | verifier/ 内 screenshotdetector Java 包、detector native 库 | 保留的可见日志验证器和正式包名 |
| module-screenshot-probe | verifier/ 内 screenshotprobe Java 包、probe native 库 | 截图 Java/NIO/JNI、已有 FD、事件与授权检查 |
| module-device-state-probe | verifier/ 内 devicestateprobe Java 包、stateprobe native 库 | 设备状态、真实 VPN 夹具、实际代理请求 |

Java/JNI 内部包名保留，减少 native 符号迁移。已发布模块的旧包名不再用于整合 APK；主模块为 `io.github.lwtdzh.appstateshield`。验证器的包名仍为 `io.github.lwtdzh.screenshotdetector`，签名保持原有身份。

`IntegratedEntry` 在 Application.attach 原方法之前读取自己的策略并安装选中的方法。`PolicyStore` 只保存关闭 ID。`PolicyProvider` 只允许 UID 读取其拥有的包名；`SettingsActivity` 是唯一正常写入口。`ModuleStatus` 是验证器内的注入标记，实际读取检查与它分开。

截图 native 库只在截图开启时加载；vpnstate 只在 VPN 开启时加载；developerstate 只在 debug 开启时加载。developer Java 设置读取与 debug Java 属性读取通过 RuntimePolicy 分别控制；proxy 有独立 Java 安装入口。0.3.0 新增 selinuxstateshield/SelinuxModule 与 selinuxstate native 库，仅在 selinux 开启时安装。验证器新增 SelinuxProbe，仍保留原包名和签名。

模块 0.2.1 仅增加截图 native 层对已有 ARM64 外部入口跳转的识别，并保留这些跳转以避免加固冲突。验证器仍为 0.2.0，工程与包名不变。保留入口的原生截图读取覆盖受限，真机启动与模拟器读取检查分别记录在 `verification/VIVO-COMPATIBILITY-0.2.1.md`。

同一份 verifier 源码通过 sampleA/sampleB flavors 提供三个 UID。所有使用私有文件目录的 native 夹具从实际 Context 传入，不依赖旧 probe APK 路径。

[人工手册](docs/TEST-MANUAL.md) 是本次整合的验收步骤，含 UI、默认/将来方法、64 组合、跨应用和真实事件。SELinux 专项由 scripts/selinux-test.py 执行，记录到 verification/selinux-0.3.0-results.json，原始恢复快照保存在仓库外。旧覆盖清单和验证结果保留；不能把旧 APK 的报告当 0.3.0 的验证证据。
