# DeveloperStateShield · 隐藏开发者与调试状态

独立的 Vector/Xposed 模块，包名 `io.github.lwtdzh.developerstateshield`，版本 `0.1.0`。向选中的应用返回开发者选项、USB 调试和无线调试未开启。系统实际设置和调试服务继续保持原状。

## 使用

安装签名 APK，在支持原生 Hook 的 Vector 中启用模块并勾选目标应用，然后强行停止并重新打开目标应用。启用和作用域由 Vector 统一管理；模块设置页仅提供说明。可与 VPN 状态模块和截图模块分别启用。

## 处理的读取路径

| 路径 | 行为 |
| --- | --- |
| `Settings.Global`、`Secure`、`System` 的 string/int/long/float 读取，包括 ForUser 与 `NameValueCache` | `development_settings_enabled`、`adb_enabled`、`adb_wifi_enabled` 返回 0 |
| `ContentResolver.call`、`ContentProviderClient.call` 的设置 GET 调用 | 返回 Bundle 的 value 改为字符串 0 |
| 设置提供程序 query，包括 Bundle 参数、仅投影 value 和全表读取 | 只替换上述设置的 value，保留其他行、顺序和调用者列集合 |
| Java `SystemProperties.get/getInt/getLong/getBoolean` | 对调试相关属性返回关闭状态 |
| Bionic `__system_property_get/read/read_callback` | 对同一组属性返回关闭状态 |

被处理的系统属性包括：`init.svc.adbd`（stopped）、`init.svc_debug_pid.adbd`（空）、`service.adb.tcp.port` / `persist.adb.tcp.port`（-1）、`persist.service.adb.enable` / `persist.sys.adb_enabled` / `sys.usb.ffs.ready`（0）。`sys.usb.state`、`sys.usb.config`、`persist.sys.usb.config` 只删除逗号列表中的 adb，保留 mtp 等其他项；列表为空时返回 none。

模块仅处理读取。写设置、普通系统属性、USB 文件传输等配置仍按原来的系统行为运行。`Debug.isDebuggerConnected` 描述当前进程是否连接调试器，属于另一种状态，本模块不修改它。

## 支持范围

支持安装于 Android 8.1 及以上，包含四种 ABI。集成验证使用 Android 16、Vector 2.2 和专用模拟器；开发者选项与 USB 调试取得实际开启的基线。该模拟器会关闭无线调试，因此无线调试开启时的实际效果暂未验证。

直接读取属性共享内存、任意原始 Binder 调用、未注入的外部 `settings/getprop` 命令、root 辅助程序和厂商私有 API 没有全面覆盖，无法承诺任意检测实现永远看不到真实状态。目标应用可能在未重启前缓存旧结果，修改作用域后需重新启动。

## 构建与验证

```sh
export JAVA_HOME=/opt/homebrew/opt/openjdk@17
export ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
./gradlew :app:assembleRelease
python3 ../scripts/sign-apk.py app/build/outputs/apk/release/app-release-unsigned.apk /tmp/DeveloperStateShield-0.1.0.apk
```

原生兼容辅助文件为项目内副本，构建不依赖其他模块。验证项目和实际结果见 [DeviceStateProbe](../module-device-state-probe/README.md)，共享关系见 [PROJECT-RELATIONSHIPS.md](../PROJECT-RELATIONSHIPS.md#device-state-protection-and-verification)。
