# AppStateShield 0.4.6 深入复核与属性对象修复

本次仔细复核原 9 个项目资料，补充 HMA-OSS、Zygisk Assistant、SUSFS LKM、ReSuSFS 的固定提交源码与 Bionic 属性对象布局。Zygisk Next/Shamiko 只按公开说明引用，未声称取得闭源实现。完整分析见《AppStateShield-设备检测深入复核与模块协作.md》和交付包 research 目录。

## 修复了什么

0.4.5 返回的属性文本与真实 prop_info 头部、serial 可能不一致。0.4.6 在本 APK 的设备 native 层创建不可变只读对象；find/foreach/find_nth 提供同一对象，长值保留完整 callback 内容与 Android 兼容槽，serial 自然读取对应对象头部。developerstate/selinuxstate 通过本 APK 内部 HandleAdapter 共用对象，不重复过滤旧缓存。

首次配置前已缓存的原指针，经本模块 read/callback 会读取当前替换值；如果应用直接读取该原指针的内存，仍可读到原始数据。已返回的合成只读对象终身保留旧值，重新 find 才读取新值；没有把旧缓存说成已经实时更新。

对象使用密封 memfd 的 PROT_READ 私有文件映射，初始化后不保留写映射和 FD。原型的“只读”是 ro.* 语义，原型 vector 内存仍可写。正式集成首次采用私有匿名只读映射时，Bionic 的 shared futex 空转，采样超时；线程栈定位到 SystemProperties::Wait。尝试密封文件后的共享映射，实际在 mmap 阶段被拒绝（EPERM）；改成私有文件映射后原始 wait 的零超时检查通过。这些失败日志均保留，不将原型结果用于证明生产映射。

机器伪装默认关闭；六项 Methods、Provider UID 权限、Vector、内核、系统分区、预设和设置交互没有修改。实现细节见源码包 docs/PROPERTY-OBJECTS-0.4.6.md；与 0.4.5 的源码对照随测试数据保存。

## 本次执行

PASS readonly layout, bounds, memoization, lifetime and 8 concurrent readers

Android 16 ARM64 / Vector / ScreenshotShield_API36：10 项定向检查通过，累计 51.9 秒；64 项共享 native 组合通过，累计 126.9 秒。每项保存时间、实际读数、APK SHA-256 和构建输入。10 项包括原始/未注入基线、首次开启、256/48 字节同进程更新、真实值等于旧替换值的反例、字段/总开关关闭，以及 debug、SELinux 和两者共用读取；最后有一次策略 UI 保存。

原始内存名称和值与 callback 一致；header/API/callback serial 一致；长值标志和相对偏移正确；read/get/nullName 值缓冲区清零、哨兵完整；枚举没有重复，find_nth 与 find 指向同一对象，越界为空。实际原系统缺失的选中属性：ro.sf.lcd_density，开启后得到对象并进入枚举。其他机型属性在该 AVD 原本存在，没有把它们冒充缺失属性基线。

更新/关闭阶段保持 PID；旧合成缓存仍能安全读取旧替换值，新查找读取当前值/恢复原值。64 组合同时保留六项方法的真实模式、VPN/USB、代理请求、原生 FD/普通文件对照及属性对象断言。截图文件属于构造夹具；不声称本次重复验证了 SystemUI 截图事件。

联测在已通过 21 项后遇到系统 Watchdog 重启。无线电服务原本未启动，验证器反复读取未选择的 Build.getSerial，让 system_server 的权限检查阻塞在电话服务，Binder 线程池耗尽。系统 ANR 和启动日志已保存。恢复临时 VPN 后，仅在后续联测档案中增加现有 serial 字段，阻止这条无关电话权限读取；APK、六项断言、原 21 项读数及原快照均未改。剩余 43 项从失败处续跑，两个执行器版本及各自 SHA-256 保留。没有把失效的模拟器无线电服务标成已恢复或通过。

四 ABI 编译和正式 APK 签名/导出/夹具排除检查通过。API 27、其他 ABI 及 vivo 没有运行结果。0.4.5 的 241+22 条纯逻辑及不变 UI 检查未重复执行，原记录保留原 APK 归属。早期失败及必要的基线冷启动保留在 previousRuns 和运行日志，未覆盖原快照。

Lint 没有错误；主模块保留 23 项警告，验证器 79 项警告。构建日志和导出检查数据随包保存。

## 为什么仍有检测无法通过，是否需要其他模块

| 检测入口 | 当前状态与可能的协作 |
|---|---|
| 公共属性对象读取 | 本次在现有模块内修复；直接系统属性区和映射来源检查仍可区分 |
| 直接 SVC 读取文件/系统状态 | 普通应用 seccomp 原型已经拦截直接 getpid；尚无通用路径代理、多线程和信号处理的生产实现 |
| 挂载及注入来源 | 普通应用 unshare 原型返回 EPERM；Zygisk Assistant 在降权前可辅助命名空间与卸载，SUSFS/LKM 可辅助内核文件视图 |
| 应用列表及直接 PMS Binder | HMA-OSS 的服务端按 UID 过滤可辅助；需要 system_server 作用域及受信配置，不是增加一个 getter |
| Vector 排除的隔离进程 | 本模块没有执行点；需要框架/更早组件；仅更换 Zygisk 实现不自动消除 Vector 排除条件 |
| ART、代码校验、GPU/HAL/TEE、服务端登录 | 更多本地 Hook 不能提供通用保证，真实证明/协议与账号风险另有数据所有者 |

辅助模块需要验证与 Vector 同时工作且本模块仍注入；没有安装或修改它们。普通 fork 会继承 native 映射，但多线程 fork 中缓存锁及配置刷新未专测；exec 会更换地址空间。未注入进程、全局属性更新通知、任意代码完整性、硬件证明和真实服务端登录仍未解决。

## 交付和环境

专用模拟器原 APK、完整数据、授权/语言、设置、作用域和 SELinux 模式已恢复；临时 VPN/文件已清理，ADB 解除 root，模拟器关闭。未操作无关 emulator-5594。vivo 未连接，没有把新版装到手机，也没有淘宝/拼多多登录成功证据。

交付包含两个同签名 APK、完整项目源码、验证器/执行器、人工说明、测试数据、构建日志、失败记录、复核资料及 SHA-256。安装后目标应用需冷启动。

| APK | SHA-256 |
|---|---|
| AppStateShield-0.4.6.apk | 47b5040d91153535688e2cfe484ecac3106eadcfc5b2069414fabd182414b8cb |
| AppStateVerifier-0.4.6.apk | bfcdb84b85ab921eff577d904f7449a8e037fffcd5f8128f0ee8ec58a1850cc9 |
