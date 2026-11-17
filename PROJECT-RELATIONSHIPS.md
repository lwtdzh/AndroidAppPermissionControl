# 工程与能力关系

0.4.13 的分类控制由 DeviceProfile.groupEnabled/get 统一计算，新增 idsEnabled 和 environmentEnabled，保留既有机型/位置控制，网络使用三档。DeviceSettingsActivity 统一渲染分类开关、状态标题及单项开关，去除模拟 SIM 的强制字段选择。DeviceHooks 的虚拟 SIM/基站构造器只填入实际允许的参数；DeviceRuntime/ModuleStatus/DeviceActivity 展示分类状态。CategoryGateTest 验证每个字段的三层条件与文档迁移，scripts/category-gates-test.py 验证保存、取消、重建及同进程读数与还原。新默认和模式语义详见 docs/CATEGORY-GATES-0.4.13.md。

0.4.12 的 EnvironmentOverview 接入新版首页与旧状态页，EnvironmentProbe 负责只读检查、私有 JSON 和逐项日志，environmentprobe.cpp 负责原生观测，AttestationRecord 负责受限 DER 解析。shared/test/AttestationRecordTest.java 测试正常/畸形证明扩展；scripts/verifier-environment-test.py 在专用 AVD 验证自动检查、刷新、未注入/注入和后台返回，并保存/恢复完整停止状态的模拟器。主模块只更新版本号，沿用 0.4.11 的 Hook。Google 证明根公钥指纹及来源保存在验证器 assets。README/AGENTS 链接 [不可修复的具体原因](docs/DETECTOR-LIMITATIONS-0.4.11.md)，不能将软件模拟器证明或局部库匹配当作真机结论、硬件能力或其他工具的全部算法。

0.4.11 的 NativeLibraries 统一五个原生库的注册与加载，移除提前注册的 assets/native_init。库仅在对应功能实际开启时经 Vector NativeAPI.recordNativeEntrypoint 注册，原生 Hook 实现不变。scripts/detector-matrix.py 仅允许专用模拟器及 Native Detector、Ruru、Key Attestation 三个包，保存截图、结果、日志、配置与模块哈希；Key Attestation 每次使用自身 Reset 重新生成证明。第三方检测结果不等同于模块自带验证器的六项屏蔽断言。

同版增加 PolicyVisibility/Receiver，为已配置包提供读取其自身 Provider 的可见性；只读服务的 UID 鉴权不变。DeviceField 增加默认未选中的 hide_module_apps，DeviceRuntime 仅在它实际生效时安装 ModuleListHooks。验证器升至 0.4.11，ModuleListProbe 与 DeviceRead 提供实际 PackageManager 模块列表、数量与普通查询对照。app/src/vectorApiStub 仅生成 compileOnly 签名 JAR，不进入正式 APK。

DeviceHooks 同版补充三个 DLKM 分区的 build.id/type/tags，统一使用选中指纹派生的值和现有 Java/native 属性适配器；不改原生读取实现。实际 Native Detector 的 Custom ROM Details 命中 vendor_dlkm 的 test-keys，修复及机型关闭对照另存最终 APK 证据。

VpnModule.INFO 同版为 getNetworkInfo 的 TYPE_VPN 返回未连接的对象副本，避免 Ruru 将 null 判断为可疑。验证器 SelinuxProbe 增加实际旧网络对象是否可用、是否连接的读取，scripts/selinux-test.py 在真实 TUN 的 64 组合中断言 VPN 开关独立，普通代理请求仍成功。第三方采集器按实际可滚动区域滑动，并比较完整 UI 树，避免文字相同但位置改变时过早结束。

0.4.5 新增 BuildFingerprint、CapacityView 和 ProfileWarnings，分别处理指纹关联字段、只读容量关系及草稿提示。VerifierIdentity 在 IntegratedEntry 上报模块状态前验证包名与签名。DeviceRuntime 的通知/轮询保持运行，设备 Java Hook 延迟到首次开启时安装。DeviceRead 增加根/分区元数据、类型化属性、内存和数据分区容量的真实 API 读取；foreignProbeDebug 和未经重签的 sampleADebug 提供包名/签名反例。定向执行器 scripts/environment-test.py 保留已通过用例，并在结束时恢复原模拟器环境。

0.4.4 在 shared/native/property-read.h 统一旧接口的完整名称解析、超长只读值兼容返回和缓冲区清理。三套 native 属性 Hook 共用它，避免共用 debug/SELinux 入口时遗漏。检测器新增六个指纹属性、三项长名称、空名称读取、返回长度与缓冲区前后哨兵检查。PropertyReadTest.cpp 做 sanitizer 边界检查；scripts/property-repair-test.py 检查实时更新、还原和完整 64 组合。[说明](docs/PROPERTY-READ-0.4.4.md)。

0.4.3 的 ModelPresets 为 DeviceProfile 和 DevicePackets 提供固定真实机型数据。小米 14 使用国际版原始固件，vivo X200 Pro mini 使用本机实测；Find X9s 移除。DeviceRuntime 将 ModelPresets 的分区属性转换同时用于 Java 和 native，检测器增加对应实际属性读取。预设不保存本机个人标识。来源见 docs/MODEL-PRESETS-0.4.3.md，定向验证脚本为 scripts/model-preset-test.py。

shared 的 ChinaRegions 提供离线省市区和三项位置参数；DevicePackets 生成同一运营商的网络与基站包、匹配的机型包和设备标识包。DeviceProfile 提供位置总开关及网络三档。DeviceHooks 经 DeviceRuntime.value 读取保存值，并对齐各档的 SIM、订阅、网络注册和同步/异步基站。检测器调用真实系统接口显示字段与状态。[行为和数据说明](docs/LOCATION-0.4.2.md)。

整合版 0.2.0 将六个独立工程迁入一个根 Gradle 工程，正式构建只交付模块和验证器两个 APK。

0.4.1 补齐原需求中的标识展示和单字段操作。DeviceOverview 在首页与旧状态页直接展示标识；DeviceActivity 提供标识优先的全部字段和搜索；DevicePresentation 解释读取错误。DeviceSampler 串行安排各前台页的两秒采样，PhoneReadService 解绑完成后才允许下一次采样。模块只调整 DeviceSettingsActivity 的单项预设与随机选择交互，Hook 和字段目录保留。受影响用例由 scripts/requirement-ui-test.py 执行；原需求对照见 docs/REQUIREMENT-AUDIT-0.4.1.md。

0.4.0 在同一工程增加机器伪装，沿用原包名和签名。shared/java 的 DeviceField/DeviceProfile 定义 46 个字段、随机生成、格式校验和不可变档案；app 的 DeviceStore/DeviceSettingsActivity 管理默认关闭的单应用档案，DeviceRuntime/DeviceHooks 与 devicestate native 库执行读取替换。六项状态屏蔽仍保存在原 PolicyStore 中。

验证器增加 DeviceActivity/DeviceRead 和 machineprobe native 库，每两秒实际读取并显示变化。DeviceProcessActivity 供同包多进程测试，受 DUMP 权限限制。verifier/src/debug 内的 Xiaomi、MSA、HeyTap、Google 方法形状只供 A/B 夹具验证，不进入正式发布包。机器伪装测试执行器为 scripts/machine-test.py；原 SELinux 执行器支持明确指定版本和单独报告路径，以保留历史证据。

0.3.1 保留工程、包名和签名关系。主模块新增默认关闭的 Launcher 别名和图标设置；验证器新增只读 ObservedState 信息条与独立 ScreenshotSession 截图次数，传统诊断入口继续保留。新增验证步骤见手册 I/V 编号，执行器为 scripts/status-ui-test.py；原有 0.3.0 的 64 组合记录仍作为历史证据，本次没有修改六种屏蔽方法的 Hook。

| 原工程 | 现位置 | 作用 |
|---|---|---|
| module-screenshot-shield | app/ 内 screenshotshield Java 包、shield native 库 | 截图回调、文件/FD、媒体、广播及其他信号屏蔽 |
| module-vpn-state-shield | app/ 内 vpnstateshield Java 包、vpnstate native 库 | VPN 观察和代理 metadata 两个独立方法 |
| module-developer-state-shield | app/ 内 developerstateshield Java 包、developerstate native 库 | 开发者选项与 USB/无线调试两个独立方法 |
| module-screenshot-detector | verifier/ 内 screenshotdetector Java 包、detector native 库 | 保留的可见日志验证器和正式包名 |
| module-screenshot-probe | verifier/ 内 screenshotprobe Java 包、probe native 库 | 截图 Java/NIO/JNI、已有 FD、事件与授权检查 |
| module-device-state-probe | verifier/ 内 devicestateprobe Java 包、stateprobe native 库 | 设备状态、真实 VPN 夹具、实际代理请求 |

Java/JNI 内部包名保留，减少 native 符号迁移。已发布模块的旧包名不再用于整合 APK；主模块为 `io.github.lwtdzh.appstateshield`。验证器的包名仍为 `io.github.lwtdzh.screenshotdetector`，签名保持原有身份。

0.4.8 仅更新主模块的机型预设编辑：DeviceSettingsActivity 把预设入口放进 model 分类，使用 DevicePackets.group("model", preset) 替换该分类字段，保留其他分类、未知字段和各开关。验证器保持 0.4.7，native 与 Provider 接口沿用 0.4.7。

0.4.9 删除 DeviceSettingsActivity 顶部的 device-random-all 按钮及跨分类刷新回调，保留既有 device-group-refresh:ids/network/model 和单项刷新。验证器、档案格式、Provider 与 native 不变。

0.4.10 合并机型预设和刷新入口，model 分类只显示 device-preset（按预设机型填写参数），由 choosePreset 选择并填入本分类数据。refreshGroup 只用于 ids/network，移除未再使用的 model 分支。

`IntegratedEntry` 在 Application.attach 原方法之前读取自己的策略并安装选中的方法。`PolicyStore` 只保存关闭 ID。`PolicyProvider` 只允许 UID 读取其拥有的包名；`SettingsActivity` 是唯一正常写入口。`ModuleStatus` 是验证器内的注入标记，实际读取检查与它分开。

截图 native 库只在截图开启时加载；vpnstate 只在 VPN 开启时加载；developerstate 只在 debug 开启时加载。developer Java 设置读取与 debug Java 属性读取通过 RuntimePolicy 分别控制；proxy 有独立 Java 安装入口。0.3.0 新增 selinuxstateshield/SelinuxModule 与 selinuxstate native 库，仅在 selinux 开启时安装。验证器新增 SelinuxProbe，仍保留原包名和签名。

模块 0.2.1 仅增加截图 native 层对已有 ARM64 外部入口跳转的识别，并保留这些跳转以避免加固冲突。验证器仍为 0.2.0，工程与包名不变。保留入口的原生截图读取覆盖受限，真机启动与模拟器读取检查分别记录在 `verification/VIVO-COMPATIBILITY-0.2.1.md`。

同一份 verifier 源码通过 sampleA/sampleB flavors 提供三个 UID。所有使用私有文件目录的 native 夹具从实际 Context 传入，不依赖旧 probe APK 路径。

0.4.6 的设备 native 层补充只读属性对象，developerstate/selinuxstate 通过 HandleAdapter 共用本进程对象映射。它们仍属于同一个主 APK，不增加外部依赖。verifier 的 machineprobe 通过系统属性接口检查原始对象、serial、枚举与缓存；debug 的能力原型只用于权限和布局研究，正式验证器排除该原型。详见 docs/PROPERTY-OBJECTS-0.4.6.md。

0.4.7 继续在当前主 APK 内实现。共享 property-area/code-view 处理属性区布局和模块自身 Hook 的代码读取；devicestate 的原始系统调用代理通过 TSYNC 同步本进程线程，使用预先准备的快照和隐藏 raw helper 避免代理递归。shield 文件适配器和设备层继续组合，截图开关独立。AttestationPrivacy 与 AttestationHooks 在既有 Keystore/KeyMint 请求中移除已选择的标识标签，保留 challenge、密钥和证书链。设备档案增加 modelEnabled，屏幕字段移入 model 分类，预设切换保留总开关。增量 JNI/Activity 均放在 verifier/src/debug，正式交付只有模块和原包名验证器；不增加外挂模块或写入系统属性。[实现与限制](docs/PROCESS-PRIVACY-0.4.7.md)。

[人工手册](docs/TEST-MANUAL.md) 是本次整合的验收步骤，含 UI、默认/将来方法、64 组合、跨应用和真实事件。SELinux 专项由 scripts/selinux-test.py 执行，记录到 verification/selinux-0.3.0-results.json，原始恢复快照保存在仓库外。旧覆盖清单和验证结果保留；不能把旧 APK 的报告当 0.3.0 的验证证据。
