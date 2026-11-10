# 0.1.0 集成验证

2026-11-09，Android 16 / Vector 2.2，专用 `ScreenshotShield_API36` 模拟器。使用已签名的两个生产 APK 和本项目 debug APK。

[`integration-0.1.0.json`](integration-0.1.0.json) 的五个 case 均通过，`passed` 和 `restored` 均为 true。系统的开发者选项和 USB 调试值为 1，真实 TEST-NET VPN 持续开启。无线调试开启时的基线不可用，未计作已验证的保护能力。

覆盖模块关闭、单独启用、同时启用和作用域外。读取路径包括 Settings/provider、Java/native properties、NetworkCapabilities/Parcelable/callback、NetworkInfo、LinkProperties、Java/native interfaces。普通 HTTPS、网络句柄、Wi-Fi、连接状态、普通设置/属性和 64 次 getifaddrs/freeifaddrs 均通过。

签名 APK 的 SHA-256：

```text
780e971b72401478f789767fc9d01ffaa752e44dc0c885a39821b3aa26bdcceb  VpnStateShield-0.1.0.apk
1e08b91c4cd99039fad07aad5ddbd24612f8c5397acbad4d1444508d8fb27e6f  DeveloperStateShield-0.1.0.apk
```

两个生产项目的 `assembleRelease`（四 ABI）和 `lintRelease` 通过；probe `assembleDebug` 通过。其他系统、厂商私有接口及未注入的进程没有在此次测试中验证。

## VPN 模块 0.1.1

[`integration-0.1.1.json`](integration-0.1.1.json) 使用最终签名 APK，五个 case 均通过，passed/restored 均为 true。追加的进程内代理测试证明：应用直接读取的代理属性不可见时，平台 HTTP 客户端仍经真实测试代理发送请求并获得 204。原有 VPN、开发者/USB 和普通操作检查继续通过。

[`vivo-citic-0.1.1.json`](vivo-citic-0.1.1.json) 记录实际 vivo 手机冷启动结果。模块启用和作用域保留，系统 VPN 仍在，动卡空间首页代理提示消失。临时追踪移除，原开关恢复；没有执行登录或金融业务。

最终 VPN APK SHA-256：`74ea751b9bab057178d428ce1e3265fadfb8973abc8df79e01d21bc8d9e8b3ca`。
