# 0.4.11 环境检测：尚不能消除的项目

这里的“不能”指当前 AppStateShield 进程内模块及本次模拟器环境下，尚不能提供可验证的修复。不是断言所有 Root 手机都必然失败。检测结果、配置和截图在交付包的 evidence 目录；完整组合见 matrix.csv。

| 工具与项目 | 实际对照与当前不能修复的原因 |
|---|---|
| Native Detector：Found Injection | 无本模块作用域时不出现；空模块进入作用域也出现。详情直接列出 Vector/ZygiskNext 已加载的原生库，实际进程映射也确认存在；当前模块未隐藏框架库枚举，尚无保持注入正常的已验证修复。 |
| Key：Unknown root certificate | 未注入对照同样使用测试证明根；模块没有受信任 CA 的签发能力，重写内容会破坏签名。 |
| Key：Attestation security level = Software | 证明安全级别来自真实密钥服务；软件模拟器无法靠进程 Hook 获得 TEE/StrongBox 的硬件隔离。 |
| Key：Keymaster/KeyMint security level = Software | 密钥管理实现也是软件；与证明安全级别是两个字段，修改机型不改变实际实现。 |
| Key：deviceLocked = false | 原镜像对照就返回 false；模块不修改启动链，也无法保留原签名而改写证明中的锁定事实。 |
| Key：verifiedBootState = Unverified | 原环境没有向密钥服务提供相应的已验证启动状态；填写系统属性不建立 AVB 验证链。 |
| Key：verifiedBootKey 全零 | 原证明未提供有效的生产启动验证密钥；任填哈希无法证明它与实际启动链相关。 |
| Key：verifiedBootHash 全零 | 原证明未提供对应受验证镜像的有效摘要；模块无法生成真实 VBMeta 关系并让原证明链签名。 |

八项中后两项是证明字段内容，检测器没有为它们分别显示顶部告警。缺失的设备 ID 证明功能另列在文末“无法验证”，不算新增检测失败。下文给出每项的完整证据和解释。

## 0.4.12 的真机补充

2026-11-15，两个 0.4.12 APK 覆盖安装到 vivo V2419A 后，自带验证器实际读到 Attestation 和 KeyMint 的安全级别均为 TrustedEnvironment（TEE），deviceLocked=false、verifiedBootState=Unverified。本次只确认安装和首页自动检查，没有在真机重新执行三款外部检测器的组合测试，也没有修改启动链或系统模式。

这份真机读数说明 Software 不是所有 Root 设备的共同结果。上表中的测试根、Software 和全零字段继续归属于原模拟器；具体真机值以 [本次安装记录](../verification/vivo-environment-0.4.12-installed.json) 为准。证明字段是本地解析结果，其信任程度还需分别核对根匹配、签名、有效期、challenge 和吊销状态。项目首页的 [限制表格](../README.md#尚不能修复的环境检测项) 为后续 Agent 的入口。

## Native Detector：Found Injection

未给检测应用设置 Vector 作用域时没有这项；进入作用域后，即使六项全部关闭、机器伪装关闭，仍出现。只执行空回调的独立 EmptyEntry 模块，以及仅注册 Application.attach 回调的对照模块，也出现同样提示。小米、vivo 机型预设及隐藏模块列表均未消除它。

N19 展开实际 Details，检测器明确返回两个路径：

- /data/adb/modules/zygisk_vector/zygisk/arm64-v8a.so
- /data/adb/modules/zygisksu/lib64/libzygisk.so

随后由未注入的 root shell 读取该目标 PID 的真实 maps，两条库路径均有可执行和可写映射；native-injection-mapped-libraries.json 保存地址、权限和路径。这些库确实在进程中，隐藏安装包查询不改变其加载状态。

因此，这个提示不依赖 AppStateShield 的截图、VPN、调试或机型功能。删除业务 Hook 不能消除由 Vector 加载模块带来的信号。直接卸载框架库会破坏模块运行；只改 maps 文本，也没有证据证明检测器所有原生枚举路径都会被处理。目前的模块没有覆盖这些框架库的加载器信息，尚无在保持注入正常的同时通过该检查的方案。

getDetections 进入 libreveny.so，公开 Java 接口未揭示具体采用 maps、动态链接器枚举还是其他内存检查。Details 已证实“返回了这些库路径”，不能把某一种内部扫描算法写成已定位。

目前没有经过这款检测器验证的通用修复。下一步需要在 Vector/LSPlant 的加载与 Hook 实现中进一步定位检测条件；只改变检测页文字、返回假结果，不能证明其他应用也看不到注入。

证据：H00-no-injection、H01-scoped-off、setup-empty-module、setup-attach-only、setup-attach-callback、H13-xiaomi-model、H14-vivo-model、J18-module-list-on、N19-native-final-injection-details、native-injection-details.json/XML/PNG、native-injection-mapped-libraries.json。

## Key Attestation：Unknown root certificate

证书链的根是 Google Test LLC / Droid Unregistered Device CA，工具没有将其识别为受信任的证明根。这项在原 AOSP 镜像对照、SukiSU + Vector 未注入基线以及注入组合中均存在。每次由检测器自身 Reset 生成新证书，排除了只读取之前证书的情况。

AppStateShield 能过滤发往 KeyMint 的指定身份请求，无法给模拟器补发一个受信任 CA 签发的证明证书。修改证书中的内容会破坏原签名；使用自行生成的密钥重签，也不能让原受信任根认可这条链。证书 subject 中的 O=TEE 文字不等于硬件安全级别。

证据：stock-control/key、H00-no-injection/key 至 H15-model-all-six/key。

## Key Attestation：Attestation security level = Software

证明扩展实际标记为 Software，工具显示不支持硬件级证明。改变 Build.MODEL、指纹和系统属性不会把模拟器里的软件 KeyMint 变成硬件隔离的 TEE 或 StrongBox。

需要具备相应硬件和有效证明配置的真实设备，才有条件得到硬件级结果。本次没有在真机验证，不能外推 vivo 手机的结果。

证据：上述 Key Attestation 对照中的 Attestation / Security level。

## Key Attestation：Keymaster / KeyMint security level = Software

这一项和上一项是两个不同的证书字段：前者表示证明安全级别，后者表示密钥管理实现的安全级别。本次两个字段均为 Software。

进程内 Hook 无法建立硬件密钥隔离，也无法靠填写机型参数改变证书中这一事实。需要更换实际密钥管理环境；改检测器读到的枚举值不构成硬件证明。

证据：上述 Key Attestation 对照中的 Keymaster / KeyMint / Security level。

## Key Attestation：deviceLocked = false / Bootloader is unlocked

这是 Root of trust 中的字段，本次也在未注入对照中出现。它由密钥服务生成的证明携带，不是读取 AppStateShield 伪装后的 Android Build 字段。

当前模块没有修改启动链或 KeyMint 的实现。应用端无法改变这个模拟器的真实启动锁定状态并同时保留原证书签名。真机重新上锁是否可行，取决于设备、镜像和启动链；本次没有实施这类系统操作。

证据：上述 Key Attestation 对照中的 Root of trust。

## Key Attestation：verifiedBootState = Unverified

证书显示未验证启动。它描述的是密钥服务所见的启动环境。模型伪装、隐藏模块 APK 和关闭调试查询都不建立 Android Verified Boot 的验证链。

要改变它，需要让实际启动环境完成相应验证并由密钥服务出具新的证明。本次模拟器在原镜像对照就具有该状态，不能归因为安装 SukiSU 导致，更不能宣称所有 Root 设备都会返回 Unverified。

证据：上述 Key Attestation 对照中的 Root of trust。

## Key Attestation：verifiedBootKey 全零

本次证明没有携带一个可据此认定为生产设备启动验证密钥的非零值。该值在未注入及不同注入组合中均保持全零。

AppStateShield 不拥有启动验证密钥，修改应用看到的系统属性也不会使真实证明改用一把有效的启动密钥。填一个看似正常的哈希不能建立它与启动镜像、证书签名的关系。

证据：上述 Key Attestation 对照中的 verifiedBootKey。

## Key Attestation：verifiedBootHash 全零

这是启动元数据的摘要字段，与 verifiedBootKey 含义不同。本次持续为全零；工具没有为它单独给出一条新的顶部告警，这里将它作为尚未解决的证明内容列出。

当前模块不能让模拟器产生与实际受验证镜像对应的有效 VBMeta 摘要，并由原证明链签名。伪造一个字符串不会改变实际启动验证。

证据：上述 Key Attestation 对照中的 verifiedBootHash。

## 不能从本次结果推导的结论

Ruru 的 Su、Busybox、Magisk 文件、原生文件检查、直接 syscall 检查和 Xposed hooks 在本次基线就显示 Not Found。没有“先检出、再消失”的对照，不能记成 AppStateShield 修复了这些项目。

隐藏模块列表只覆盖识别出的 Xposed 模块在所 Hook 的 Java PackageManager 接口中的可见性。直接 Binder、子进程 pm、原生文件检查、隔离进程、安装列表变动及框架内存痕迹各自需要证据；Ruru 的一项通过不代表所有方法都被隐藏。

Key Attestation 的设备 ID/设备属性证明另列为无法验证：本次系统没有 android.software.device_id_attestation 功能，真实菜单不提供 Attest device props。C0409ua.java 第 59 行明确按该功能决定支持情况。AppStateShield 可以减少已选身份请求字段，但不能补出模拟器缺失的硬件 ID 证明功能，也不能把合成标识变成真实硬件认可的身份。它不是此次检测页新发现的异常，不能混入已实测的八项结果。

已解决项目：Native Detector 启动闪退；Key Attestation 配置读取失败；Ruru 的 Xposed Modules；Ruru 的调试开启提示；Ruru 真实 VPN 下的空网络对象可疑提示；Native Detector 的 Debug Fingerprint；可选 Custom ROM 检测命中的 vendor_dlkm test-keys。调试提示和 Debug Fingerprint 使用已有调试控制和机型预设，属于本次验证有效的已有能力。
