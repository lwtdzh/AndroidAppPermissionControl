# AppStateShield 0.4.0 · 模拟器测试报告

模块和验证器均为 0.4.0。运行环境是专用 ScreenshotShield_API36、Android 16 / API 36、ARM64、Vector。四 ABI 构建通过与运行检查分别记录。

设备字段检查：PASS 26113 device field assertions。机器伪装已选择字段、设置操作、实时更新与多应用隔离按下表执行；原有六种屏蔽在机器伪装开启时完成 64 种组合。
有耗时记录的 59 个组合，从首项开始到末项结束共 38.6 秒（含批量配置）；先前保留结果没有补写耗时。

| 执行条目 | 结果 | 当次模块 / 验证器 SHA-256 前 12 位 |
|---|---|---|
| D00-capture | 通过；原始快照 | 原始快照 / 原始快照 |
| D01-upgrade-default | 通过；本次 APK 的实际验证 | da53746db954 / 9fc720795b4c |
| D02-drafts-rotation | 通过；本次 APK 的实际验证 | da53746db954 / 9fc720795b4c |
| D03-xiaomi-smoke | 通过；本次 APK 的实际验证 | da53746db954 / 9fc720795b4c |
| D03-oppo-preset | 通过；本次 APK 的实际验证 | da53746db954 / 9fc720795b4c |
| D04-invalid-input | 通过；本次 APK 的实际验证 | da53746db954 / 9fc720795b4c |
| D04-valid-manual-imei | 通过；本次 APK 的实际验证 | da53746db954 / 9fc720795b4c |
| D04-single-preset-group-random | 通过；本次 APK 的实际验证 | da53746db954 / 9fc720795b4c |
| D05-imei-live | 通过；本次 APK 的实际验证 | da53746db954 / 9fc720795b4c |
| D05-stable-reads | 通过；本次 APK 的实际验证 | da53746db954 / 9fc720795b4c |
| D05-D10-live-fields-OEM-fixtures | 通过；本次 APK 的实际验证 | da53746db954 / 9fc720795b4c |
| D07-apps-processes-delete | 通过；本次 APK 的实际验证 | da53746db954 / 9fc720795b4c |
| D08-D12-multiple-paths | 通过；本次 APK 的实际验证 | da53746db954 / 9fc720795b4c |
| D06-fieldoff-masteroff | 通过；本次 APK 的实际验证 | da53746db954 / 9fc720795b4c |
| D06-all-fields-off | 通过；本次 APK 的实际验证 | da53746db954 / 9fc720795b4c |
| D14-optional-environment | 通过；本次 APK 的实际验证 | da53746db954 / 9fc720795b4c |
| D13-display-rotation | 通过；本次 APK 的实际验证 | da53746db954 / 9fc720795b4c |
| D15-two-second-foreground | 通过；本次 APK 的实际验证 | da53746db954 / 9fc720795b4c |
| D15-cached-binder | 通过；本次 APK 的实际验证 | da53746db954 / 9fc720795b4c |
| D16-D17-legacy-regression | 通过；本次 APK 的实际验证 | da53746db954 / 9fc720795b4c |
| D16-actual-system-screenshot | 通过；本次 APK 的实际验证 | da53746db954 / 9fc720795b4c |
| D08-native-callback-ownership | 通过；本次 APK 的实际验证 | da53746db954 / 9fc720795b4c |
| D18-restored | 通过；本次 APK 的实际验证 | da53746db954 / 9fc720795b4c |

原始数据见 machine-0.4.0-results.json、selinux-0.4.0-results.json；安装包 SHA-256 见随包校验文件。报告保留先前失败记录，最新结果与修复后重测分开。
已通过的最终 APK 结果在中断后原样保留，剩余组合使用专用模拟器批量配置。跨 APK 复用须通过构建时源码、读取断言、环境和本次集成对照，保留原 APK 哈希；缺少这些资料的历史结果不用于交付判断。
首次开启的失败原始证据保存在 machine-activation-before-fix-0.4.0.json：当时 Java 机型已变化，deviceNative 为 false，三个原生入口仍返回模拟器机型。修复后须确认新配置版本、Java 字段和三个原生入口一致，才允许生成交付包。
后台进程结束的问题另有 machine-cached-binder-before-fix-0.4.0.json：真实电话 Binder 请求超时后仍等待回复。电话检测现由同包、同 UID 的辅助进程调用，结果保留来源、辅助 PID 和配置版本，结束辅助进程释放未完成请求；检测页保留 PID。模块周期查询也在页面后台停止。已用未伪装电话请求、系统缓存冻结、返回页面的同 PID 对照重测。
批量还原的第一次比较在 IMEI 项失败，该次未保存前后读数，无法据此确认原因或认定真实 IMEI 泄漏。保留失败记录后，增加前后完整快照，仅定向执行还原：同 PID 下 46 个原值/原错误、Java/native 属性全部一致，三阶段电话辅助进程与主进程配置版本相同；IMEI 的原始与还原结果均为电话 API 超时。完整诊断见 machine-all-fields-off-diagnostic-0.4.0.json，不能把超时结果写成真实 IMEI 可读基线。

## 实际核对范围

- 默认关闭、按应用保存、两种机型预设、单字段预设、手工编辑、IMEI 校验、已选择随机字段刷新、取消/丢弃、旋转保留草稿。
- 同 PID 的 IMEI / Android ID / OAID / 坐标读取、静态字段还原、单字段关闭、主开关关闭、删除档案、多 UID 与同包多进程。
- 保持机器伪装主开关开启，用专用模拟器批量配置关闭全部字段；46 个字段逐项对比总开关关闭时的原值/原错误，随后恢复原档案的字段和值。手工 IMEI 保存和界面交互仍走真实 UI。
- Java 属性与 Bionic get/read/callback，Display 横竖屏及资源 metrics，总内存/容量/语言/时区/传感器选择，普通文件和显式 Locale/TimeZone。
- 明确命名的 vivo/Xiaomi/MSA/HeyTap/Google 调试夹具；定位 getter、对象回调、原始 Parcel 字段与 NMEA，LTE 标识的 Parcel。
- 真实 SELinux Permissive/Enforcing、普通 FD/EOF/错误、原生截图文件/已有 FD、syscall 六参数、clone 新栈、实际代理请求、HTTPS 与 Provider 越权读写拒绝。
- 机器伪装开启时，真实 SystemUI 截图保存与两种截图回调按关闭、开启、重新关闭截图屏蔽执行对照。

## 尚未证明的项目

- AOSP 没有真实厂商标识服务；SDK 形状夹具不能证明 vivo、OPPO、小米各 ROM 的全部路径。
- 模拟器电话 HAL 存在等待不返回的入口；合成基站对象证明适配器行为，不能当真实 modem 回调验证。定位/NMEA 的对象夹具也不能代替真实 GPS 事件。
- Widevine 实例在此模拟器不支持，DRM ID 缺少可读取基线。native 网卡地址若未返回 AF_PACKET 数据，只能确认接口列表释放测试。
- 应用私有缓存、反射/JNI 直读原对象字段、ART 内联、任意 Binder/内核直读、硬件认证、公网 IP、账号和服务端关联仍可能暴露真实信息。需要按具体应用继续验证。
- 定位权限撤回、不同 ROM 的 Wi-Fi 扫描和实机窗口布局留在人工计划中，未以模拟器空数据判作通过。

本轮只在专用模拟器执行；最终已恢复原状态并关闭专用 AVD。

## 每个字段的观察情况

未开启时一栏仅记录接口是否可读；开启后返回保存值不代表这个模拟器拥有真实 SIM、GPS 或厂商服务。厂商夹具与正式验证器分别标注。

| 字段 | 未开启时 | 开启后的观察 | 读取入口 |
|---|---|---|---|
| 品牌 | 可读取 | 正式验证器接口返回保存值 | Build.BRAND |
| 制造商 | 可读取 | 正式验证器接口返回保存值 | Build.MANUFACTURER |
| 型号 | 可读取 | 正式验证器接口返回保存值 | Build.MODEL |
| 设备代号 | 可读取 | 正式验证器接口返回保存值 | Build.DEVICE |
| 产品代号 | 可读取 | 正式验证器接口返回保存值 | Build.PRODUCT |
| 主板 | 可读取 | 正式验证器接口返回保存值 | Build.BOARD |
| 硬件平台 | 可读取 | 正式验证器接口返回保存值 | Build.HARDWARE |
| 固件指纹 | 可读取 | 正式验证器接口返回保存值 | Build.FINGERPRINT |
| Android 版本文本 | 可读取 | 正式验证器接口返回保存值 | Build.VERSION.RELEASE |
| 固件版本 | 可读取 | 正式验证器接口返回保存值 | Build.VERSION.INCREMENTAL |
| IMEI · 卡槽 1 | 无数据 | 正式验证器接口返回保存值 | TelephonyManager.getImei(0) (same-UID phone worker) |
| IMEI · 卡槽 2 | 无数据 | 正式验证器接口返回保存值 | TelephonyManager.getImei(1) (same-UID phone worker) |
| MEID | 无数据 | 正式验证器接口返回保存值 | TelephonyManager.getMeid (same-UID phone worker) |
| 设备序列号 | 可读取 | 正式验证器接口返回保存值 | Build.getSerial |
| Android ID | 可读取 | 正式验证器接口返回保存值 | Settings.Secure.getString |
| OAID | 无法读取：SecurityException | 厂商/广告 SDK 夹具通过；真实服务未验证 | vivo IdProvider query |
| VAID | 无法读取：SecurityException | 厂商/广告 SDK 夹具通过；真实服务未验证 | vivo IdProvider query |
| AAID | 无法读取：SecurityException | 厂商/广告 SDK 夹具通过；真实服务未验证 | vivo IdProvider query |
| Google 广告 ID | 无法读取：ClassNotFoundException | 厂商/广告 SDK 夹具通过；真实服务未验证 | Google AdvertisingIdClient (if SDK is present) |
| MediaDrm 设备 ID | 无法读取：UnsupportedSchemeException | 无法核对：UnsupportedSchemeException | MediaDrm Widevine deviceUniqueId |
| 网卡 MAC | 可读取 | 正式验证器接口返回保存值 | WifiInfo.getMacAddress |
| 蓝牙地址 | 可读取 | 正式验证器接口返回保存值 | BluetoothAdapter.getAddress |
| Wi-Fi 名称 | 可读取 | 正式验证器接口返回保存值 | WifiInfo.getSSID |
| Wi-Fi BSSID | 可读取 | 正式验证器接口返回保存值 | WifiInfo.getBSSID |
| IMSI | 无数据 | 正式验证器接口返回保存值 | TelephonyManager.getSubscriberId (same-UID phone worker) |
| SIM 序列号 | 无数据 | 正式验证器接口返回保存值 | TelephonyManager.getSimSerialNumber (same-UID phone worker) |
| 手机号读数 | 无数据 | 正式验证器接口返回保存值 | TelephonyManager.getLine1Number (same-UID phone worker) |
| 运营商名称 | 可读取 | 正式验证器接口返回保存值 | TelephonyManager.getNetworkOperatorName (same-UID phone worker) |
| MCC | 无数据 | 正式验证器接口返回保存值 | TelephonyManager.getNetworkOperator / MCC (same-UID phone worker) |
| MNC | 无数据 | 正式验证器接口返回保存值 | TelephonyManager.getNetworkOperator / MNC (same-UID phone worker) |
| 位置区 LAC | 无法读取：TimeoutException | 正式验证器接口返回保存值 | TelephonyManager.getCellLocation.getLac (same-UID phone worker) |
| 基站 CI / NCI | 无法读取：TimeoutException | 正式验证器接口返回保存值 | TelephonyManager.getCellLocation.getCid (same-UID phone worker) |
| 跟踪区 TAC | 无法读取：TimeoutException | 正式验证器接口返回保存值 | TelephonyManager.getAllCellInfo / LTE (same-UID phone worker) |
| 物理小区 PCI | 无法读取：TimeoutException | 正式验证器接口返回保存值 | TelephonyManager.getAllCellInfo / LTE (same-UID phone worker) |
| 信号强度 | 无法读取：TimeoutException | 正式验证器接口返回保存值 | TelephonyManager.getAllCellInfo / LTE (same-UID phone worker) |
| 纬度 | 无数据 | 正式验证器接口返回保存值 | LocationManager.getLastKnownLocation(gps) |
| 经度 | 无数据 | 正式验证器接口返回保存值 | LocationManager.getLastKnownLocation(gps) |
| 定位精度 | 无数据 | 正式验证器接口返回保存值 | LocationManager.getLastKnownLocation(gps) |
| 竖屏宽度 | 可读取 | 正式验证器接口返回保存值 | Display.getRealMetrics |
| 竖屏高度 | 可读取 | 正式验证器接口返回保存值 | Display.getRealMetrics |
| 逻辑密度 | 可读取 | 正式验证器接口返回保存值 | Display.getRealMetrics |
| 总内存 | 可读取 | 单独勾选后返回保存值；测试后关闭 | ActivityManager.MemoryInfo.totalMem bytes |
| 存储总容量 | 可读取 | 单独勾选后返回保存值；测试后关闭 | StatFs.getTotalBytes bytes |
| 默认时区 | 可读取 | 单独勾选后返回保存值；测试后关闭 | TimeZone.getDefault |
| 默认语言 | 可读取 | 单独勾选后返回保存值；测试后关闭 | Locale.getDefault |
| 隐藏传感器列表 | 可读取 | 单独勾选后返回保存值；测试后关闭 | SensorManager.getSensorList count |
