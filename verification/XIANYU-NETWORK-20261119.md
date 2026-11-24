# 闲鱼加入作用域后无法联网：模拟器对照记录

2026-11-19 的第一阶段模拟器记录。**这一阶段尚未复现用户报告的断网，未修改生产 Hook。**

用户后续说明分身清数据并重建设置后卡住退出。新的首次初始化路径已在模拟器复现 ANR，修复版及检查结果见 [文件读取代理修复记录](XIANYU-BROKER-FIX-20261119.md)。vivo 重试安装已成功，原配置生效的冷启动进入首页；本文的首页联网观察保留原 APK 和原阶段，不作为修复版全部请求正常的证明。

后续用户已明确故障发生在 vivo 分身，且取得实际 ANR 退出记录。真机开关对照、原配置恢复及当前未确认的根因见 [闲鱼分身 ANR 补充记录](XIANYU-CLONE-ANR-20261119.md)；下文保留此前模拟器阶段的观察。

## 实际观察

从真机只读取得闲鱼 7.28.86.1（versionCode 529）的原签名 base 和三个 split，在模拟器安装，未重打包。apksigner 校验通过，签名证书 SHA-256 为 e4c15e30502f8da0e878e0fe73877403b8d99f8f761809507a6512ecfed84909。

模块使用此前构建的 AppStateShield-default-selection.apk，SHA-256 为 57c1a94c24c1c366f47f68671f720497405e3a278b5e976490abbb9e8b6c72ea。运行平台是 API36 / ARM64。本轮没有重新构建。

| 对照 | 观察 |
|---|---|
| 未加入作用域 | 首页出现商品图片、文字和价格 |
| 加入作用域，六项全关，机器伪装关闭 | 首页出现商品；目标进程记录 policy loaded=true、enabled=[] |
| 六项全开，机器伪装关闭 | 首页出现商品；策略六项全开，native 与 compatibility 初始化成功 |
| 清除本轮新装闲鱼的数据，再全开六项 | 完成初次提示后出现商品；排除了此前首页磁盘缓存 |
| 六项全开，复制真机分身的机器档案 | 首页出现商品 |
| 保留设备标识伪装，关闭网络伪装 | 首页出现商品 |
| AOSP 临时分身 user10，未注入 | 首页出现商品，分身进程没有模块加载记录 |
| AOSP 临时分身 user10，六项全开并使用真机机器档案 | 首页出现商品；分身自己的策略读取成功，设备层记录 native ready hooks=3 objects=1 |
| 全开六项后进入商品详情 | 出现登录页，未登录，详情请求未验证 |

上述观察只说明匿名公开首页可以加载。未记录 MTOP 请求响应、签名参数或认证数据，不能据此证明登录后的全部功能正常。SecurityGuard 异常在未注入且首页能加载时也出现，不能单凭异常名称把它认定为断网原因。

代表性策略通过真实设置 UI 保存；后续对照使用专用模拟器的原子配置夹具。复制到模拟器的是闲鱼分身在模块中保存的设备档案，没有复制闲鱼账号数据。临时分身为 AOSP user10，其行为不能直接等同于 vivo user999。

## 真机只读配置发现

18:07 的配置快照显示，模块作用域只包含 **com.taobao.idlefish / user999**。该分身的六项屏蔽均开启，机器伪装开启，idsEnabled=true、networkMode=no_sim；机型、环境、位置分类关闭。

18:11 读取已有进程时，闲鱼主进程 UID 为 10400，属于主用户。没有发现 user999 的闲鱼进程，也没有取得正在失败的注入进程或服务器错误码。两次只读快照之间是否有用户操作，未作假定。

因此，需要核实用户当时报错的是主应用还是分身，以及发生故障的页面和错误提示。当前证据不能把主用户进程与 user999 的模块配置合并成同一个故障样本。

只读检查时当前默认网络为已验证的 Wi-Fi；没有当前 VPN NetworkAgent。dumpsys 中的历史 VPN 请求不作为当前 VPN 的证据。

## 调用链检查

对原 APK 定向反编译 anet.channel.status.NetworkStatusHelper 和 NetworkStatusMonitor：

- NetworkStatusHelper.isConnected 会检查 NetworkInfo.isConnected。
- NetworkStatusMonitor.getNetworkInfo 使用 ConnectivityManager.getActiveNetworkInfo，并可能缓存结果。
- NetworkStatusMonitor.getNetworkStatus(Network) 使用 ConnectivityManager.getNetworkInfo(Network)。

这些入口与 VpnModule 的 NetworkInfo 返回处理有关，但本轮没有取得该链路在故障现场返回空值或断开状态的运行证据，也没有确定请求签名失败。反编译输出保存在私有测试目录；不把静态可疑点写成已确认根因。

## 恢复与下一步

模拟器已停止，完整 AVD 恢复到测试前快照；逐文件 SHA-256、大小、权限、目录和符号链接清单一致，ramdisk 哈希一致。原 APK、配置、其他模块作用域、授权、服务和夹具由原磁盘整体恢复。emulator-5594 未操作。

另修正此前授权真机设置验证在恢复文件时留下的归属错误：主用户模块 device_profiles.xml 从 root:root / 640 恢复到 10469:10469 / 660，文件内容 SHA-256 不变。此处没有闲鱼主用户机器档案，user999 的档案和作用域没有修改，不能把这一修正当作闲鱼断网修复。

尚需实际故障实例和页面信息。对上故障实例后，应取得一次失败请求的脱敏错误码，再决定是否需要对真机作短时配置对照。本轮没有新增生产代码，无需重跑 64 组合。

机器可读证据：[xianyu-network-20261119-results.json](xianyu-network-20261119-results.json)。此前恢复问题的修正记录：[vivo-preference-ownership-restored-20261119.json](vivo-preference-ownership-restored-20261119.json)。

私有证据目录：/Users/bytedance/Library/Application Support/ScreenshotShield/xianyu-network-20261119。仅当前报告及脱敏结果进入工作区，未提交或推送。
