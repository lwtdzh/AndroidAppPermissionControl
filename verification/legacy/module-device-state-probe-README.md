# DeviceStateProbe · 设备状态测试

独立测试应用，包名 `io.github.lwtdzh.devicestateprobe`，版本 `0.1.0`。配套验证 VPN 状态模块和开发者/调试状态模块。生产模块不依赖本项目的源码、构建或运行服务。

## 测试内容

通过 `VpnService` 建立真实 TUN，地址和路由只使用 TEST-NET `192.0.2.0/24`，不接管普通 Internet 流量。VPN 服务使用 `:vpn` 独立进程；测试脚本只重启主读取进程，以保持同一个 VPN 和 Network 对象。

脚本临时开启模拟器的开发者选项和 USB 调试，检查系统真实值，再比较以下五种情况：模块关闭、只隐藏 VPN、只隐藏开发者与调试、两个模块同时启用、两个模块启用但应用不在作用域。

读取路径包含 Settings 数字与字符串、设置提供程序 call/query/Bundle query/value-only projection、原生 property get/read/callback、Java 系统属性、NetworkCapabilities、Parcelable、系统网络回调、旧版 NetworkInfo、LinkProperties 和 Java/原生网卡枚举。普通操作检查包含网络句柄、Wi-Fi transport、实际 HTTPS 204、普通设置、SDK 属性、getpid，以及 64 次网卡分配/释放。

VPN 模块 0.1.1 的配套检查还构建一个进程内 HTTP 代理测试服务，确认应用读取不到代理 host/port 时，平台 HTTP 客户端仍能发送实际请求到该代理并获得 204。代理属性属于明确构建的测试配置，与真实 TUN 基线分别记录；不会配置手机或模拟器的全局代理。

测试应用 targetSdk 28，以便反射诊断系统属性接口；这不代表生产模块采用旧 targetSdk。测试无线调试字段的返回值，但模拟器无法保持其开启状态，不能据此证明无线调试开启时的保护效果。

## 运行

```sh
export JAVA_HOME=/opt/homebrew/opt/openjdk@17
export ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
./gradlew :app:assembleDebug
```

使用已准备的专用 `ScreenshotShield_API36` 模拟器 `emulator-5584`，先执行 `adb -s emulator-5584 root`。安装本项目 debug APK 和两个已签名模块 APK，确认 Vector 能识别模块后运行：

```sh
python3 scripts/emulator-test.py --output verification/integration-0.1.0.json
```

脚本拒绝其他模拟器和真实手机，也拒绝覆盖已经存在的 VPN。它通过系统 app-op 授予本测试 APK 的 VPN 建立权限，获得真实服务授权。完成后停止测试 VPN，恢复原设置、模块启用状态、目标应用原作用域和 VPN app-op。安装的测试 APK 会保留。新安装模块原来一般是禁用状态，测试会恢复此状态。

结果位于 [verification/integration-0.1.0.json](verification/integration-0.1.0.json)。共享关系和变更时需要复查的项目见 [PROJECT-RELATIONSHIPS.md](../PROJECT-RELATIONSHIPS.md#device-state-protection-and-verification)。

针对 VPN 模块 0.1.1 的追加结果记录在 [verification/integration-0.1.1.json](verification/integration-0.1.1.json)。
