# AppStateShield 0.4.11：三款环境检测器组合实测

测试日期：2026-11-15。仅使用专用 Android 16 / API 36 / ARM64 模拟器 ScreenshotShield_API36（emulator-5584），没有操作 vivo 真机。

交付包汇总 81 次有效第三方检测观察：H 主矩阵 48 次、J 模块列表 4 次、K 可选检查 8 次、L DLKM/恢复 11 次、N 最终 VPN/完整配置/注入详情 10 次。故障隔离和未完整采集的 N00 另记诊断对照，不进入这个数量。最终验证器另有 67 项六方法/模式/权限检查。

## 结论

已经修复 Native Detector 的启动闪退、Key Attestation 读取不到已保存配置的问题，并新增默认关闭的“隐藏模块应用列表”。Ruru 的 Xposed Modules 可从 Found 变成 Not Found；已有 debug 开关能消除 Ruru 调试提示；已有小米/vivo 机型预设能消除 Native Detector 的 Debug Fingerprint。同版补齐遗漏的 DLKM 分区构建元数据，处理可选 Custom ROM 检测的 test-keys 提示。最后针对真实 VPN 连接修正旧网络 API 的返回形状，避免空对象被 Ruru 判为可疑。

Native Detector 仍识别出 Vector 的模块注入。Key Attestation 仍显示未知证明根、软件安全级别和未验证启动。后者在未注入对照中已经存在。每个尚未解决的项目及证据见 [逐项原因](../docs/DETECTOR-LIMITATIONS-0.4.11.md)。

这三款工具不是同一套检查。Ruru 没有检出 Xposed hooks，不能推导出 Native Detector 也应该通过；Key Attestation 的签名证明也不是修改 Build 参数就会随之改变的普通属性。

## 实际环境与来源

| 项目 | 本次版本与配置 |
|---|---|
| 系统 | Android 16 / API 36，AOSP ARM64，kernel 6.6.66 |
| Root | SukiSU Ultra 4.3.0-r2 / KernelSU 41150，官方 6.6 LKM 在现有内核上加载 |
| Zygisk | ZygiskNext 1.5.3，实际状态显示 KernelSU 41150、Vector 已加载 |
| Vector | 官方 2.2 / 3080 Release |
| Native Detector | 官方 7.7.0，签名验证通过；主矩阵 Experimental / Custom ROM 均关闭 |
| Ruru | 官方 1.1.1 / version code 15 |
| Key Attestation | 官方 1.8.4 / version code 198；每次使用自身 Reset 新建证明 |
| 模块与验证器 | 最终 0.4.11；H、J/K、L、N 分别绑定 APK 哈希 |

资产的 URL、大小、SHA-256、APK 证书摘要在交付包 sources.json。Vector ZIP 与 GitHub 官方 digest 完全一致后才使用；没有把未核验的本地文件当成官方版本。

上游发布来源：

- https://github.com/SukiSU-Ultra/SukiSU-Ultra/releases/tag/v4.3.0-r2
- https://github.com/Dr-TSNG/ZygiskNext/releases/tag/v1.5.3
- https://github.com/JingMatrix/Vector/releases/tag/v2.2
- https://github.com/reveny/Android-Native-Root-Detector/releases/tag/v7.7.0
- https://github.com/byxiaorun/Ruru/releases/tag/v1.1.1
- https://github.com/vvb2060/KeyAttestation/releases/tag/v1.8.4

## 主矩阵：16 个配置 × 3 款工具

六项指 screenshot、vpn、proxy、developer、debug、selinux。机器伪装单独测试，未将它变成第七个默认开启的方法。

| 配置 | Native Detector | Ruru | Key Attestation |
|---|---|---|---|
| H00 无本模块作用域 | Debug Fingerprint；无 Found Injection | Xposed Modules Found；调试 Suspicious | 未知根、Software、解锁/Unverified |
| H01 已注入，六项与机器全关 | 新增 Found Injection | 与 H00 相同 | 与 H00 相同 |
| H02 仅 developer | 指纹 + 注入 | USB 调试提示仍在 | 同上 |
| H03 仅 debug | 指纹 + 注入 | 调试及 Setting Props 变为 Not Found；模块列表仍 Found | 同上 |
| H04 仅 proxy | 指纹 + 注入 | 调试提示仍在 | 同上 |
| H05 仅 screenshot | 指纹 + 注入，正常启动 | 调试提示仍在 | 同上 |
| H06 仅 vpn | 指纹 + 注入 | 调试提示仍在 | 同上 |
| H07 仅 selinux | 指纹 + 注入 | 调试提示仍在 | 同上 |
| H08 developer + debug | 指纹 + 注入 | 调试提示消失 | 同上 |
| H09 vpn + proxy | 指纹 + 注入 | 调试提示仍在 | 同上 |
| H10 六项全开 | 指纹 + 注入，正常启动 | 调试提示消失 | 同上 |
| H11 机器开启但未选择字段 | 指纹 + 注入 | 模块列表仍 Found | 同上 |
| H12 标识/无 SIM，机型总开关关 | 指纹 + 注入 | 模块列表仍 Found | 同上 |
| H13 小米 14 机型总开关开 | 指纹提示消失；仍 Found Injection | 模块列表仍 Found | 同上 |
| H14 vivo 机型总开关开 | 指纹提示消失；仍 Found Injection | 模块列表仍 Found | 同上 |
| H15 vivo + 六项全开 | 仅剩 Found Injection | 调试提示消失；模块列表仍 Found | 同上 |

主矩阵 48 次均进入检测页，没有闪退。native 功能另核对 native ready 日志和实际读取；policy loaded=false 的旧试验没有记成有效配置测试。H01/H03 的部分元数据字段是在执行后才加入采集器的，保留原始 JSON，由对应完整日志和当时安装包补充核验，不倒填旧结果。

Ruru 的 Xposed hooks、Su/Busybox/Magisk 文件、PM 和原生文件检查在无注入基线即为 Not Found，48 次中没有变成 Found。此结果仅说明这款工具在此环境下未检出，不能宣称这些 Root 检测由模块成功隐藏。

主矩阵未建立 VPN/代理/截图等真实阳性，因此不会把“无提示”记成这些功能有效。最终六项测试使用实际 TUN、真实调试开启、Permissive/Enforcing 和截图/普通文件夹具另做组合断言。

## 修复一：Native Detector 的原生启动闪退

之前 assets/native_init 无条件列出五个 native 库。Vector 在 detector 初始化前注册原生加载拦截，Native Detector 在 libreveny.so 的 0xe7590 位置崩溃。

隔离实验保留相同 Java 代码和 native 库，只删除 native_init，检测器就能启动。分别仅注册 shield、vpnstate、developerstate、selinuxstate、devicestate 五个单项，均重现崩溃。因此不是某一个业务功能的返回值导致，也不能用“能启动但 native 根本没有加载”的包宣称修好。

最终删除静态注册清单；NativeLibraries.load 在实际需要库时调用 Vector 2.2 的 NativeAPI.recordNativeEntrypoint，再加载库。直接引用 compileOnly API 类型，兼容 Vector 对类型描述符的重定位；字符串反射试验无法适应该重定位，已放弃。API stub 不进入 APK。

单项、六项全开和机型组合能正常启动，并有对应 native ready 记录。没有修改检测器 APK、签名或显示结果。

## 修复二：Key Attestation 读不到配置

Key Attestation 没有应用列表查询权限；模块包信息虽然显示 forceQueryable=true，系统实际 forceQueryable 列表却没有本模块。模块设置页已打开、Provider 已运行时，目标仍报告 IllegalArgumentException，策略回退到默认全开。这种样本不能算“仅开 debug”通过。

PolicyVisibility 给已保存策略/档案的包授予只读前缀 URI 权限，建立解析 Provider 所需的包可见性。保存、设置页启动、升级和启动广播会重新建立授权。Provider 仍按 Binder UID 校验包名，query、insert、update、delete 和非 read call 均拒绝。

修复后的 Key 样本实际加载预期方法，仍正常新建证明。证书结果保持原样，这与配置读取修复是两个不同问题。

## 修复三：Ruru 枚举模块 APK

Ruru 的 Xposed Modules 与进程 Hook 检查分开。模块已安装时，无作用域也能枚举其 APK 元数据。

新增机器伪装 → 其他环境 → 隐藏模块应用列表，默认未选中。ModuleListHooks 只依据实际 ApplicationInfo.metaData 中 xposedmodule 的 Boolean true 建立集合，不按应用名猜测。过滤受 Hook 的列表、包名直接查询及 Intent 解析，保留自身、普通应用、未识别对象和原查询异常。

J16 为关闭对照；J17 通过真实设置页搜索、选择、保存该字段，Ruru 的 Xposed Modules 变为 Not Found。J18 验证 Native Detector 与 Key Attestation 均正常启动，注入提示和证明状态仍在。

验证器通过真实 PackageManager 查询确认模块从应用/包/Intent 列表中消失，直接查询返回不存在，Settings 和自身保持可见；字段关、重新开、机器总开关关，均在同一 PID 恢复正确列表。证据见 module-list-integration.json。

最后一次总开关恢复最初遇到的是测试 fixture 缓存竞争：可见目标在写入结束前重新启动 Provider，使 SharedPreferences 缓存旧文件。测试执行器改为在原子写入和回读之后再次清除 Provider 进程；同一 APK、原 PID 恢复成功。失败日志保留，没有修改产品逻辑掩盖问题。

## 修复四：可选 Custom ROM 检查

K02/K03 同时打开 Native Detector 的 Experimental 和 Custom ROM 选项并冷启动：无注入基线和 vivo 机型伪装均出现 Detected Custom ROM。点击该项展开 Details，实际文字为 Property: ro.vendor_dlkm.build.tags, Value: test-keys。

DeviceHooks 原来列出 system、vendor、product、odm、system_ext 的构建属性，遗漏了 DLKM 分区。补充 system_dlkm/vendor_dlkm/odm_dlkm 的 build.id/type/tags，沿用既有指纹派生和机型总开关。没有改变原生 Hook 或修改检测页结果；这些派生值属于模拟属性，不冒充已核验的 OEM 分区固件。

L 系列使用补齐 DLKM、尚未修改 VPN 的 APK，对照两个机型预设、关闭机型总开关，以及三款检测器的默认选项。K 系列保留修改前结果和其 APK 哈希。L04 的 Ruru 虽已隐藏模块，却仍在真实 VPN 环境中显示 Setting Props/Vpn Connected Suspicious；因此 L 不能当作最终全部通过的记录。

Key Attestation 的 Attest device props 在这台模拟器中不可选。实际系统功能列表缺少 android.software.device_id_attestation，检测器 C0409ua 构造函数在第 59 行依据该功能隐藏选项。Use attest key 开与关的真实菜单均未提供它。key-device-props-capability.json 和菜单 XML/PNG 保存此证据；本次不声称验证了这款工具发出的设备 ID 证明请求。

## 修复五：真实 VPN 下的 Ruru 可疑提示

Ruru 1.1.1 的实际 MainActivity 字节码调用 getNetworkInfo(TYPE_VPN)，既判断 isConnectedOrConnecting，也把空结果记为可疑。AppStateShield 原来将 VPN 对象直接返回 null，虽然连接信息消失，仍会触发这项提示。源码证据为交付包 controls/ruru-mainactivity.smali 的 700–780 行。

VpnModule.INFO 改为复制系统提供的 NetworkInfo，将 DetailedState 设为 DISCONNECTED。只处理 getNetworkInfo 的 VPN 对象；原生接口过滤、活动网络和列表处理保持原逻辑。目标看到“系统支持该网络类型，但当前未连接”，真实 TUN 仍运行。系统原异常保持不变，副本构造失败记录警告并回退为空结果，其他系统需再验证。

N 系列绑定最终 APK，设置真实 TUN 阳性对照：无作用域、注入全关、仅 vpn、仅 debug，以及 vpn/debug/developer 组合；随后检查三款检测器的完整配置和 Native Detector 的可选检测。主矩阵 H 的 48 个原始结果原样保留，不修改其 APK 哈希。

N00/N01/N03 仍显示 Vpn Connected Suspicious；N02/N04 的 vpn not connected 为 Not Found，shell 确认真实 TUN 在全部五项中始终存在。N05 的 Ruru 同时显示 Xposed Modules、Setting Props、vpn not connected 为 Not Found。N05 的 Key 自身 Reset 后生成新的 SIGN 证书，仍显示相同 Software、未知根和未验证启动；早期 H 的 ATTEST KEY 证书保持各自原始记录。

N06 开启 Experimental 与 Custom ROM 后，仅剩 Found Injection。N19 展开详情实际列出 Vector 与 ZygiskNext 两个已加载库路径；随后 root shell 在该目标 PID 的真实 maps 中确认两者存在。具体原生枚举算法未确定，不能把返回的路径当成已知算法。限制清单保存这项尚未修复的具体原因。

最初 N00 的采集未滚动到页面底部就结束，缺少 VPN 字段，因此断言失败；保存为 N00-incomplete-capture 诊断记录。采集器改为按实际可滚动区域滑动、比较完整 XML 位置并确认连续未变化，随后重新采集。它是采集失败，不能计作检测项目通过。

## APK 与证据对应关系

| 阶段 | 模块 SHA-256 | 对应证据 |
|---|---|---|
| H 主矩阵 | 4fde076904f840aac5c146bdeeba6030362f2e5dcdcde2810e433865cd5c6920 | 48 次主矩阵 |
| J/K 模块列表与可选检查，尚未补 DLKM | b66cb24890f72cce5f5795e38efc50c614bec2c3107f687906c31bbad803e311 | J16–J18、K00–K03 |
| L 已补 DLKM、未改 VPN | e7650a5d0684ee1a6d1d36c9b3544e97e6460747329364ab8d7356c1f445d5aa | DLKM 修复与关闭恢复；Ruru VPN 仍可疑 |
| N 最终模块 APK | 2928c4bc594aee08cf799057e3e42fc73ed496e8a87cb689b58ff5bb5b5282a0 | 真实 VPN 对照、最终三款检测、最终六项组合 |
| 最终验证器 APK | 99c412ccbd5f773e04d9dcdce32a50214a8fab591045a507e83440753f783d50 | 旧网络对象、模块列表和最终六项读取 |

## 结果如何核验

交付包保存 matrix.json / matrix.csv、各检测页 XML/PNG、目标进程日志、完整配置、每次已安装模块 SHA-256、主矩阵与最终构建输入、隔离实验源码和最终两个 APK。所有 Key 样本记录自身 Reset、新 challenge 和创建时间。

最终构建、lint、四 ABI 编译成功；DeviceFieldTest 的 26121 条断言及 ModelGateTest 的 128 条断言通过。四 ABI 编译不等于四 ABI 运行测试；本次运行证据只有 ARM64/API 36。

最终 APK 的 64 种六项组合、真实 Enforcing/Permissive 两项未注入基线，以及 UID/写入隔离一项，共 67 项全部通过。逐组合检查真实 TUN 的 Java/native 可见性、旧网络对象是否存在/连接、开发者与调试状态、原生库按需加载、SELinux 读取和普通 FD/EOF/错误对照、实际代理请求 204、截图文件与普通文件夹具。直接 syscall 在真实 Permissive 下仍读取真实模式，作为已有读取限制保留；本轮没有把它标成成功屏蔽，也没有替代完整的真实截图/选图权限测试。

最终产物审查确认两个 APK 沿用原签名、均含四 ABI，排除 OEM/debug 原生夹具；主模块没有 assets/native_init，DEX 定义中没有 compileOnly NativeAPI stub。76 项原生导出符号核对通过，模块/验证器 lint 均无 Error/Fatal；现存 Warning 分别为 23/79。版本及包名分别为 AppStateShield 0.4.11 / io.github.lwtdzh.appstateshield、AppStateVerifier 0.4.11 / io.github.lwtdzh.screenshotdetector。

模块列表 UI 操作复用 L17 的真实编辑/保存记录，DeviceSettingsActivity、DeviceStore 和 ModuleListHooks 的构建时源码哈希与最终包一致。最终包安装后重新冷启动验证器，在同一 PID 执行默认关闭、字段开、字段关、再开、机器总开关关五项读取与恢复。旧的中断六项测试另存 provenance/final-methods-before-vpn.json，不能混入最终通过数量。

完整 AVD 在测试前以停止状态复制，测试完成后整体恢复；恢复记录随交付包保存。原模拟器 APK、数据、模块、作用域和设置以原完整 AVD 为准。
