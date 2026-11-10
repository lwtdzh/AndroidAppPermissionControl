# VpnStateShield · 隐藏 VPN 状态

独立的 Vector/Xposed 模块，包名 `io.github.lwtdzh.vpnstateshield`，版本 `0.1.1`。在被选中的应用进程中，把常用 Android 接口返回的 VPN 状态改为未开启，并隐藏应用直接读取的系统代理配置。实际 VPN、Network 对象和网络路由继续使用原来的配置。

## 使用

1. 安装签名 APK，需要支持原生 Hook 的 Vector。
2. 在 Vector 中启用模块，勾选需要隐藏 VPN 状态的应用。
3. 强行停止并重新打开目标应用。目标应用的所有需要保护的进程都应由框架注入。

模块设置页提供说明；启用和作用域由 Vector 统一管理。可以与 DeveloperStateShield、ScreenshotShield 分别启用。

## 处理的读取路径

| 路径 | 返回给目标应用的结果 |
| --- | --- |
| `ConnectivityManager.getNetworkCapabilities` 和生成的 `IConnectivityManager` 代理 | 移除 `TRANSPORT_VPN`，保留其他 transport 和能力，并设置 `NOT_VPN` |
| `NetworkCapabilities` getter、Parcelable 读取、系统网络回调 | VPN transport 为 false；VPN transport info 被移除 |
| VPN 类型的旧版 `NetworkInfo` 查询 | VPN 条目不可见；普通网络条目保留 |
| `LinkProperties`、Parcelable、字符串和路由 interface | 隧道 interface 名称不可见 |
| Java `NetworkInterface` 列举、名称/索引/地址查询和子网卡列举 | 过滤常见隧道名称 |
| Bionic `getifaddrs` / `freeifaddrs` | 过滤隧道网卡；普通网卡保留；成对释放原始分配 |
| `System.getProperty/getProperties` 与实际系统 `Properties` 对象 | 应用读取代理 host/port 时得到缺省值，普通属性保留 |
| `ConnectivityManager` / Binder 代理查询、`LinkProperties.getHttpProxy` 和旧版 `Proxy` 查询 | 应用直接读取时显示没有代理 |

隧道名称规则是 `tun`、`tap`、`ppp`、`ipsec`、`vti`、`wg`、`utun` 后接数字，以及 `utun`。应用使用这些名称的其他虚拟网卡也会被隐藏。模块不把应用绑定到 VPN 之外的网络。

代理读取由 `ProxyHooks` 处理。平台 HTTP/Socket、OkHttp、Chromium/WebView 和系统代理初始化路径继续读取真实配置，普通应用查询得到无代理的结果。这是通过调用栈识别读者实现的；应用自定义网络库如果直接用这些查询结果构造代理，可能改为直连，但仍受系统 VPN 路由约束。任意外部工具、原始 Binder 和私有检测路径不在该处理范围内。

0.1.1 修复了 vivo 上动卡空间的“正在使用网络代理”提示。运行时记录确认 `com.citiccard.dkkj.util.NetworkUtils.g` 及 `com.citiccard.fps.risk.DeviceHelper.checkProxy` 会读取 `http.proxyHost` / `http.proxyPort`；0.1.0 没有隐藏这些属性。该提示与应用的 VPN 提示是两条独立分支。新版保留模块启用状态和作用域，实际手机首页验证通过，VPN 继续开启；没有执行登录或金融业务。

## 支持范围

支持安装于 Android 8.1 及以上；APK 包含 arm64-v8a、armeabi-v7a、x86_64、x86。实际集成验证使用 Android 16、Vector 2.2 和专用模拟器。

进程内 Hook 覆盖上述读取接口。直接解析 `/proc` 或 `/sys`、直接使用 netlink/syscall、任意原始 Binder 协议、执行未注入的外部命令、root 辅助程序、厂商私有 API，以及服务端根据出口判断 VPN，都没有全面覆盖。因此无法承诺任意检测实现永远看不到真实状态。系统进程和 VPN 提供程序应保持在模块作用域之外。

原生代码内的 `vector-hooks.h` 是已有链接器兼容处理的本地副本，生产构建不读取其他子项目。

## 构建与验证

```sh
export JAVA_HOME=/opt/homebrew/opt/openjdk@17
export ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
./gradlew :app:assembleRelease
python3 ../scripts/sign-apk.py app/build/outputs/apk/release/app-release-unsigned.apk /tmp/VpnStateShield-0.1.1.apk
```

配套验证项目是 [DeviceStateProbe](../module-device-state-probe/README.md)。它实际建立只路由 TEST-NET 的 VPN，以未保护、单模块、双模块、作用域外几种情况比较状态和普通联网。共享关系和测试顺序见 [PROJECT-RELATIONSHIPS.md](../PROJECT-RELATIONSHIPS.md#device-state-protection-and-verification)。
