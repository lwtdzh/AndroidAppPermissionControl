# 验证器的系统环境检查

从 0.4.12 起，验证器每次进入首页自动检查一次系统环境。首页的“展开检查详情”显示逐项读数和限制，结果也打印到首页日志及 Logcat 的 EnvironmentProbe 标签。截图计数只接收原截图事件，环境输出不会增加它。API 28–33 的旧状态页也显示同一检查面板。

“重新检查环境”重新生成一次读数；页面后台停止自动请求，正在进行的密钥服务调用完成后清理本次密钥，旧页面不会更新。检查在后台线程串行执行，不每两秒生成证明。私有结果文件为 files/environment-result.json，使用 AtomicFile 完整替换，包含版本、时间、PID、注入状态、逐项检查、计数和受限的原始读数。没有新增导出读取或写入接口。

| 检查 | 本次读取内容与解释 |
|---|---|
| Root 文件 | 固定 Su、Busybox、Magisk、KernelSU 目录的 Os.stat、libc stat、直接 faccessat syscall。只要一条路径实际存在就显示信号；权限拒绝与其他错误显示无法确认。不会执行 su。 |
| 注入库 | 当前进程 maps 与 dl_iterate_phdr 中的已知 Vector/Zygisk/Xposed/LSPlant 等库路径。检查不包含 ART Hook 扫描、匿名映射、被隐藏的库或所有检测器算法。 |
| Xposed | 当前 ClassLoader 中的 XposedBridge；PackageManager 可见的 xposedmodule 元数据数量。空查询不证明框架未安装。 |
| 构建属性 | Java Build.TAGS、原生 build tags/type、debuggable/secure、三项 DLKM tags。启动属性只作参考，属性读取可能受伪装影响。 |
| 普通状态 | 当前应用可见的 VPN、代理、开发者选项、USB/无线调试、调试器与 SELinux。开启状态是信号，单项不能证明 Root。 |
| 证明 | AndroidKeyStore 生成普通 EC P-256 签名密钥，使用新随机 challenge，读取实际证明链。逐级检查签名、签发者名称和有效期，从根向叶寻找第一个 Android 证明扩展，再解析 challenge、证明/KeyMint 安全级别及 RootOfTrust。 |
| 根信任 | 用 DER SubjectPublicKeyInfo 的 SHA-256 与 Android Developers 公布的 Google RSA、2026 ECDSA 根公钥匹配。清单日期和来源保存在 assets 中。厂商根或新根可能未收录。 |
| 清理和能力 | finally 只删除本次随机别名；不导出私钥、整份证书、设备 ID 或挑战。不申请 StrongBox；普通证明结果不能说明所有 StrongBox 能力。设备 ID 与 StrongBox 支持仅查询系统功能标记。 |

“本项检查通过”指该条读取没有发现指定信号；“发现信号”指确有对应本地读数；“无法确认”指缺失、权限拒绝、不支持或信任信息不完整；“参考信息”不会被当成通过证明。证明字段使用本地解析值：未知根、链错误或 challenge 不匹配时，不能把字段当作可信事实。非零启动哈希也不能单独证明生产启动链。

恢复后的 Magisk/Vector 专用模拟器给出一个实际反例：模块标记明确显示 injected=true，而已知库路径扫描没有匹配。shell 的真实 maps 同样没有对应命名路径，存在 memfd/jit-cache 映射，不能把这些通用映射直接认作某个具体框架库。它与 0.4.11 的 SukiSU/ZygiskNext 实测环境不同；后者确实返回具名框架库。两份记录各自保留来源，路径扫描通过不代表独立排除了注入。

检测器不访问网络，不检查证书在线吊销，不验证完整 PKIX 策略，也不调用 Play Integrity。处于注入进程中的本地检查仍可能被 Hook。签名链检查、Google 根匹配、挑战匹配和硬件级别是不同项目；需要服务端挑战与可信服务端验证时，应使用独立的远端验证流程。

尚不能修复的八项原因和证据保存在 [0.4.11 的逐项限制](DETECTOR-LIMITATIONS-0.4.11.md)。原模拟器的 Software、未锁定启动和测试根不能当成 vivo 的实测值，也不能通过改检测器文案宣称已经修复。

修改范围仅为验证器读数与展示，模块只升版本。定向检查 DER 正常/畸形数据、四 ABI 编译、未注入/注入读数、手动刷新、后台返回和临时密钥清理；旧 64 组合仍保持原报告归属，不因为 APK 哈希变化而重复整轮。
