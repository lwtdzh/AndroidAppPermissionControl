# AppStateShield / 应用状态验证器 0.4.13

每个字段的已保存参数同时受机器伪装总开关、分类总控制与单项开关约束。设备标识、机型与系统、位置和其他环境有独立总开关，新档案默认关闭；标题显式显示已开启或已关闭。网络与基站保留已关闭、模拟 SIM 卡、模拟无 SIM 卡三档，标题显示选中的状态。

关闭分类保留参数和单项选择。统一刷新、填写机型预设、保存与旋转保持分类状态。模拟 SIM 提供虚拟有卡/注册状态，但不强制选中字段；虚拟对象未选参数使用空值或未知值。模拟无 SIM 清除蜂窝信息，同时保留设备标识分类控制的 IMEI，以及独立选择的 Wi-Fi/蓝牙参数。

旧档案缺失的新分类控制默认关闭，既有机型、位置和网络显式状态保留。未知字段继续保存，缺少字段目录元数据时不会应用。实现和使用说明见 docs/CATEGORY-GATES-0.4.13.md。

## 本次验证

两个正式 APK 构建与 lint 通过，四 ABI 编译完成，原签名保持，调试厂商夹具未进入正式 APK。所有 native 库与 0.4.12 的字节相同。本次实际运行环境为专用 emulator-5584 / ScreenshotShield_API36，API36 ARM64；四 ABI 编译结果不代表另外三种 ABI 的运行验证。

JVM 检查：

- CategoryGateTest：PASS 1332 category, three-gate, network-mode and migration assertions
- ModelGateTest：PASS 130 new model master, merged display and default-selection assertions
- RegionProfileTest：PASS 18178 region/profile assertions; 3209 districts, 358 explicit missing points
- EnvironmentProfileTest：PASS 241 metadata, gates, warnings and capacity assertions
- ModelPresetTest：PASS 249 stock-preset, partition-property and legacy-migration assertions
- DeviceFieldTest：PASS 26121 device field assertions（字段格式与生成规则未修改，沿用既有结果，本轮未重跑）

下表为本次最终 APK 的 13 个实测用例，原始快照、失败记录和每次耗时保留在 evidence/。设置页保存、单项开关、丢弃、旋转、刷新和预设通过真实 UI 操作；批量运行对照采用专用模拟器的原子配置夹具，保留其他应用配置，不增加正式写接口。

执行器修正了展开列表的滚动查找、电脑与恢复后模拟器时钟不同的判断，以及配置 Provider 停止时的客户端依赖。系统日志明确记录第一次重启由停止 Provider 引发；批量写入前返回桌面并等候界面停止回调后，最终 10 项读取对照全部使用 PID 19956。原失败记录和第一次通过的对照另存为 runtimeSessions，未覆盖 UI 结果。交付截图为经过界面核对的设置页默认关闭状态；读数对照以对应 JSON 快照为准。

| 用例 | 结果 | 耗时（秒） |
|---|---|---|
| C01-default-headers-ui-save | 通过 | 65.022 |
| C02-field-gates-rotation-discard | 通过 | 210.517 |
| C03-three-states-refresh-preset | 通过 | 185.109 |
| C04-real-category-off-baseline | 通过 | 6.01 |
| C05-all-categories-enabled | 通过 | 9.031 |
| C06-fields-off-virtual-defaults | 通过 | 9.944 |
| C07-same-pid-values-update | 通过 | 6.695 |
| C08-category-off-restoration | 通过 | 7.345 |
| C09-network-full-sync-async-parcel | 通过 | 6.655 |
| C10-network-partial-fields | 通过 | 6.992 |
| C11-no-sim | 通过 | 10.93 |
| C12-master-off-restoration | 通过 | 7.544 |
| C13-legacy-missing-flags | 通过 | 9.187 |

真实分类关闭基线中传感器列表非空。启用后 Android ID、机型、定位、内存、时区与 Wi-Fi 读数改变，Java/native 机型读数一致；字段关闭、分类关闭及机器总开关关闭恢复原读数或原异常，主 PID 保持不变。网络检查覆盖全部字段、部分字段、未选字段默认值、同步/异步读取及 Parcel 还原。返回的虚拟 SIM 状态与是否覆盖保存参数分别核对。

此正式验证器 UID 的原生 getifaddrs 没有返回 MAC 项，因此本轮原生网卡 MAC 缺少非空基线，未将空集合记作隐藏成功；Wi-Fi 地址通过 WifiInfo 与 Java wlan0 读取核对。原生机型的 get/read/callback 三种属性入口另有非空基线并进行实际对照。原系统电话与基站读取的超时保持为异常；虚拟 SIM 模式需要给出明确数值、对象和回调，不能以超时通过。

本次只改变机器档案和相关网络虚拟对象。六项状态屏蔽的策略、入口和共享 native Hook 未修改，因此没有重新执行旧 64 组合，也没有将旧运行记录当成本次 APK 的新证据。厂商 SDK 和其他 ROM 未在本轮运行；原有注入痕迹、硬件证明和 AVB 限制仍见项目说明。

## 环境与交付

完整原模拟器磁盘已恢复，文件树、权限及每个文件 SHA-256 与开始前一致，ramdisk 未修改，模拟器已停止；其他模拟器未操作。

发布文件见仓库的 v0.4.13 Release 页面。手机安装与模拟器测试分开记录，覆盖安装不等于完成真机功能验证。两个 0.4.13 APK 已在 vivo V2419A 完成覆盖安装，文件哈希、版本、UID、原配置、权限及 Vector 作用域均已核对；此次安装未追加真机功能测试。

- AppStateShield-0.4.13.apk：主模块，版本代码 23。
- AppStateVerifier-0.4.13.apk：检测器，版本代码 19。
- evidence/：本次运行、JVM、构建、最终产物审计与恢复记录。
- source/：本次修改文件和两个执行脚本。
- SHA256SUMS.txt：全部交付文件的校验值。
