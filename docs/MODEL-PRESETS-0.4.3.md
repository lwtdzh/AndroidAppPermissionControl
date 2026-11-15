# 真实机型预设：小米 14 与 vivo X200 Pro mini

预设只提供小米 14 国际版和 vivo X200 Pro mini。Find X9s 已移除。机型信息固定使用以下原始数据，点击统一刷新恢复这份数据，不再生成 privacy_xxx、PRIVATE 固件号或随机设备代号。

| 字段 | 小米 14 国际版 | vivo X200 Pro mini 本机 |
|---|---|---|
| 品牌 / 厂商 | Xiaomi / Xiaomi | vivo / vivo |
| 型号 | 23127PN0CG | V2419A |
| 设备代号 | houji | PD2419 |
| 产品代号 | houji_global | PD2419 |
| 主板 | houji | k6991v1_64 |
| 硬件 | qcom | mt6991 |
| Android 版本 | 15 | 16 |
| 固件增量版本 | OS2.0.201.0.VNCMIXM | compiler261012170621 |
| 竖屏分辨率 | 1200 × 2670 | 1080 × 2344 |
| 当前逻辑密度 | 480 | 480 |

小米数据来自 Jiovanni-dump/xiaomi_houji_dump 固定提交 d0218f10a72390912c6fff1517b71918243f2a52。根指纹另用小米官方 OTA 的 metadata 核对；hardware 来自同一 OTA 的 vendor_boot bootconfig，明确写有 androidboot.hardware=qcom。读取 vendor_boot 只下载包含头部和 bootconfig 的两个操作，分别校验 OTA manifest 中的 SHA-256；未下载完整分区，不声称验证完整分区哈希。

vivo 数据于 2026-11-13 UTC 通过未注入的 adb shell getprop、wm size 和 wm density 从用户本机采集。只保留机型和系统字段，排除序列号、IMEI、Android ID、MAC、Wi-Fi 名称和账号。原始白名单结果随来源资产保存。

根指纹分别为：

```text
Xiaomi/houji_global/houji:15/AQ3A.240627.003/OS2.0.201.0.VNCMIXM:user/release-keys
vivo/PD2419/PD2419:16/BP2A.250605.031.A3_V000L1/compiler261012170621:user/release-keys
```

分区名称与根名称不同是原始固件的实际结果。小米 vendor 使用 mivendor，system_ext 使用 missi；vivo vendor 使用 PD2415，system_ext 使用 mssi_64_64only_cn_armv82。各分区指纹也分别保存。vivo 的 wm density 是 480，ro.sf.lcd_density 是 560，两种入口分别返回对应值。

设备标识、Wi-Fi MAC、蓝牙地址和 Wi-Fi 名称与具体机型没有固定对应关系。它们继续生成合成值并保存，不把用户本机的个人标识分发给其他应用。网络与基站仍由独立档位和开关控制。

旧小米档案只替换模块曾生成的占位代号、固件指纹及配套默认值，保留手工参数、个人标识和未知字段。旧 OPPO 档案转为自定义并移除已知占位字段，保留其他配置。已有档案不会自动换成 vivo；用户选择预设并保存后才切换。

预设修改 Android 版本文本，不更改运行时 SDK_INT。旧原生 __system_property_read 接口返回的属性名最多 31 字节；现有过滤器按返回的名称查表，较长名称仍可能返回本机原值。本次实测 ro.product.system_ext.manufacturer 的 get/callback 正确替换，旧 read 保留模拟器原值 unknown。旧 get/read 的值缓冲区最多返回 91 字节，小米 vendor 指纹在这两个入口中被截断；Java 和原生 callback 返回完整指纹。两项均单独记录为现有读取限制。应用检查 Android API 版本、内核、硬件认证或其他未适配入口时，仍可能看到本机特征；真实机型参数不等于已经验证所有检测入口。

原始来源文件位于 app/src/main/assets/model-presets-source.json、model-vivo-source.json 和 model-xiaomi-boot-source.json；验证记录位于 verification/model-presets-0.4.3-results.json。
