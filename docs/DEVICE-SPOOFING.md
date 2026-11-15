# 机器伪装：实现与逐项核对

机器伪装独立于六项状态屏蔽。未配置应用默认关闭；不是 Methods 的第七个默认开启 ID。单个应用开启后，只有已选择且已填写的字段可替换。机型预设使用真实固件数据；个人标识独立生成，保存后读取时不重新随机。

0.4.11 共享目录新增第 47 项“隐藏模块应用列表”，放在“其他环境”，默认不选中。机器总开关开启、字段已选择且值为 true 时，按实际 xposedmodule Boolean 元数据过滤 PackageManager 中的模块应用。关闭字段或机器总开关恢复查询。应用安装集合在进程启动时建立；安装新模块后需要冷启动。它不能隐藏 pm 子进程、直接文件/IPC 查询或运行中的 Vector 注入；验证器用实际查询显示可见模块数量。

## 配置与更新

DeviceField 是共享字段目录，定义 ID、分组、格式校验与随机生成。DeviceProfile 保存独立 enabled、selected、values、preset 和 revision。DeviceStore 使用单份同步 SharedPreferences 提交档案，通过当前包名的 URI 通知后续读取。原 PolicyStore 和 RuntimePolicy 保留六项默认开启规则。

PolicyProvider 的 read 仍验证 Binder 调用 UID 必须拥有请求包名。它只返回本包档案，不提供写操作。新增档案不改变 Vector 作用域。设置页不能使用另一个应用的随机值作默认值。

目标进程在 Application.attach 前取得档案，首次开启机器伪装时安装独立的读取拦截。从未开启时不安装设备 Java Hook；首次开启后再关闭，已安装的 Hook 返回原接口结果。配置通知和轮询更新当前档案；读方法使用不可变快照。旧六项屏蔽继续在启动时读取配置。静态 Build 值需同时保存原始值，以便关闭后恢复，但 ART 内联、SDK 缓存和启动时判断仍应提示冷启动。

0.4.5 从选定的完整指纹同步 Build.ID、TYPE、TAGS 和根/分区对应属性。真实预设各分区保留自己的指纹及编译编号；手工指纹只按其内容推导，不补造数据。非标准指纹保留原输入，设置页提示无法同步元数据。关闭指纹字段后关联元数据一起恢复。

可选容量适配同步总量与剩余量。ActivityManager 的可用内存和低内存阈值按实际占比显示；数据分区 StatFs 的块数/字节数以及普通 File 容量按同一占比显示。根据文件系统设备号识别数据分区，系统分区和读取失败保留原结果。磁盘、RAM 和内核读数本身不变；应用在首次开启前已缓存的对象或数值仍需冷启动。

验证器状态上报只接受固定三个自有包名及固定发布签名，同时要求加载包名与实际 Context 包名一致。其他应用提供同名 ModuleStatus 类也不会被接管。此校验只保护状态接口，不代表 Vector 注入痕迹已经隐藏。

周期轮询仅在 Activity 可见时进行，返回页面立即刷新；后台服务保留保存通知。验证器的电话接口由同包、同 UID 的短生命周期辅助进程实际读取，结果注明辅助 PID 和配置版本，其余接口仍由检测页进程读取。电话 Binder 请求没有回复时结束辅助进程并显示超时，避免检测页在后台因遗留 Binder 请求被系统结束。

首次在运行中的进程开启时，先更新静态字段并完成原生库加载及 JNI 数据提交，再公布新的配置版本。检测器观察到新版本时，原生读取也应已经就绪；不能以 Java 字段先变化作为整份档案已生效的证据。

MCC 与 MNC 都已选择时，运营商代码直接使用保存值，不等待真实电话服务。只选择其中一项时，仍从原始运营商代码保留未选择的部分；原调用失败或格式无效时保留其结果。

## 预设与字段

小米 14 国际型号 23127PN0CG、代号 houji、产品 houji_global、主板 houji、硬件 qcom、1200 × 2670、逻辑密度 480；vivo X200 Pro mini 本机型号 V2419A、代号和产品 PD2419、主板 k6991v1_64、硬件 mt6991、1080 × 2344、当前逻辑密度 480。vivo 的 ro.sf.lcd_density 实测为 560，按该属性的原值单独保存。固件版本、指纹和分区属性来自原始数据，统一刷新不生成随机代号。Find X9s 已移除；旧档案转为自定义，仅清理模块曾生成的占位代号。Android 版本文本不修改 SDK_INT。预设位置为上海市中心 31.2304 / 121.4737，不随真实定位移动。完整来源见 [0.4.3 预设说明](MODEL-PRESETS-0.4.3.md)。

IMEI 以合成前缀 99 开头并生成 Luhn 校验位；这不证明任何运营商或设备认证有效。两个卡槽独立生成。OAID、VAID、AAID 和 GAID 各自生成 UUID；不能合并成同一个标识。MAC 使用本地管理单播地址。总内存、总存储、语言、时区、隐藏传感器和 DRM ID 需单独选择，避免预设立即影响所有应用功能。

## 读取入口和验证要求

下表是实现及测试目录。最终通过情况以当前版本执行报告为准，不能把目录本身当成已经验证。

| 类别 | 需要检查的读取入口 | 对照要求 |
|---|---|---|
| 型号与固件 | Build 静态字段、SystemProperties get、native 三种 property API | 开启、修改、关闭和冷启动；检查属性默认值 |
| IMEI / SIM / 序列号 | TelephonyManager 多卡方法、SubscriptionInfo、Build.getSerial | 原始权限错误单独记录；非法卡槽保留原语义 |
| Android ID | Settings.Secure getString / getStringForUser、ContentResolver settings 查询 | 不能泛改全部 settings 字符串 |
| OAID 等 | vivo 标识 Provider、小米 IdProvider、MSA IdSupplier 的具体实现、指定厂商 AIDL Proxy、Google Info | 厂商夹具与真 ROM 分别记录；不泛改 Parcel 或所有 Binder 请求 |
| DRM | MediaDrm.getPropertyByteArray 的 deviceUniqueId | 其他属性与普通 DRM 操作不改 |
| Wi-Fi / 蓝牙 | WifiInfo、ScanResult、BluetoothAdapter、NetworkInterface、native getifaddrs | 普通接口、地址长度和内存释放 |
| 基站 / 信号 | CellLocation、CellIdentity、CellSignalStrength 与 Telephony 回调 | 直接方法、返回对象和回调分别检查 |
| 位置 | Location getters、LocationManager 最后定位、回调、Parcel 对象及 NMEA | 不把空定位当成原始可读基线 |
| 屏幕 | Display size / metrics、Resources metrics、Point / Display.Mode | 横竖屏、多窗口、点击与普通布局 |
| 环境 | ActivityManager.MemoryInfo、StatFs 总容量、Locale / TimeZone 默认值、SensorManager | 可用内存、剩余容量与普通文件保持可用 |

native property 与原有 developerstate / selinuxstate 组合过滤，避免 Vector 同一符号重复 Hook。新增处理不得修改截图 syscall 汇编、clone、已保存加固入口、SELinux FD 所有权或错误/EOF 语义。

debug A/B 含明确命名的 SDK 形状与 Location/NMEA 对象夹具；sampleA 还提供受 DUMP 权限限制的 vivo 游标形状。只在专用 AOSP 模拟器安装，安装前须确认没有真实同名 Provider。正式 primary release 不含这些类和 Provider。夹具用于检查 OAID/VAID/AAID 独立性、供应者回调对象、坐标序列化与普通方法对照，不能替代真实 ROM、调制解调器或 GPS 事件。

Location 和基站对象的 getter、toString 与已适配的序列化会替换读数；目标直接用反射或 JNI 读取原对象私有字段，仍可能绕过这些入口。现有实现没有通用的字段访问虚拟化。应用自己保存的对象、字符串缓存及不在表内的 SDK 需按具体目标检查。

## 实际限制

系统服务端 Binder 直读、SDK 自有缓存、内核文件与直接系统调用、GPU / CPU 指令与硬件能力、硬件认证、公网 IP、账号及服务端已有关系，均不能仅凭上述入口替换宣称消除。未来增加读取路径时继续在此目录标明并加入对照，不在主干代码里猜测任意字符串类型。

常见 CellIdentity/CellSignalStrength 的 getter、toString/Parcel 已适配已选择的字段，但未选择的其他成员和不同 ROM 的 Binder 格式仍保留原语义；只关闭单个定位字段时，未选择的坐标维度仍是真值。Wi-Fi 扫描结果的 SSID/BSSID 可替换，其余频率/信号等指纹仍保留。逻辑分辨率不改变系统窗口边界、截屏像素或真实 GPU 参数。应结合具体应用的实际读取入口验证，不能据此宣称“完全匿名”。
