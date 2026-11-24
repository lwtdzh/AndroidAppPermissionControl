# 闲鱼清数据后首次启动：文件读取代理优化与未通过的验收

**本页保留旧 broker 候选的历史记录。用户于 2026-11-20 反馈该候选未修复完整四步首次启动。随后 caller-read 新候选于同日 14:52 在 vivo 完整走完四步，同意后进入可操作首页，见 [最新真机验收](XIANYU-VIVO-FOUR-STEP-20261120.md)。** 旧候选此前保留真机数据的冷启动不算该流程通过。固定流程见 [人工测试手册](../docs/TEST-MANUAL.md#闲鱼分身清数据后的首次启动)。

11:14 的[补充复现记录](XIANYU-FOUR-STEP-20261120.md)已完成模拟器真实清数据、作用域保存、配置删除重建和首次初始化，首页与搜索可操作。分身侧 Vector 无法激活，实际使用主侧 Vector 的分身用户页；vivo 当时未连接 ADB，完整真机验收仍未通过。

专用模拟器 emulator-5584 / API36 / ARM64。修复版已完成清数据后的首次初始化，进入 user10 的 MainActivity，无新增 ANR。APK 属性区开启/更新/关闭、64 种屏蔽组合与相关原生文件检查已通过，原模拟器磁盘已恢复。用户授权重试后，vivo 覆盖安装成功；恢复模块配置可见性后，分身读取原配置、进入首页并持续运行 67.18 秒，无新增退出记录。

用户提供的新复现步骤是清除分身数据、重新切换 Vector 作用域、清除模块中该应用的状态，再重建个性化设置。此前已有数据的冷启动观察不能覆盖这条首次初始化路径。[之前的真机记录](XIANYU-CLONE-ANR-20261119.md) 保留为历史证据。

## 故障证据

使用真机复制的原始签名闲鱼 base/split APK，在模拟器 user10 建立独立测试应用，复制用户此次重建后的设置参数和开关。六项方法全部开启，机器伪装开启，标识符开启，网络 no_sim，其他分类关闭。参数、46 项选择和未知字段不公开。

修复前，清数据后的 PID 4142 和 13996 分别留下 21:45:15、21:59:49 的 ANR。关闭机器伪装、仍开启六项方法的首次初始化 PID 11266 未产生新增 ANR。故障中的 ART 栈确认：

- 主线程从 InitActivity.enterAppAfterPrivacyAgree 进入 BlinkNewEngine，等待启动任务或 SecurityGuard 初始化锁。
- SecurityGuard 工作线程经 JNICLibrary.doCommandNative、libsgmainso-6.7.260202.so 调用模块的文件读取包装器。
- PID 13996 / sysTid 14118 的三个模块 PC 为 selinuxstate 的 device_raw_return、enforceFd/device_io::link 和 h_fread。它们证明初始化经过文件拦截，不单凭这一瞬间的栈认定 readlink 死锁。

另一轮带 ptrace 的采样 PID 18969 记录大量 read/readlinkat，主线程等待 SecurityGuard 同一个锁。该轮还产生 GPU 读管道的 ANR；带跟踪的耗时不能当作未干预启动时间。原始应用缓冲区没有保存，统计、模块偏移与 ART 栈位于仓库外的私有诊断目录。

## 修改

旧代理在每次普通 read/mmap 前，打开并读取 /proc/&lt;tid&gt;/status 来校验线程，再复制 FD、fstat 和 readlink。libc 设备读取还会解析 FD 路径，部分自身 mem 读取重新加载属性区和解析动态库符号。这些工作随普通读取重复发生。

修改 app/src/main/cpp/device-syscall-view.h 和 devicestate.cpp：

- 通过 /proc/self/task/&lt;tid&gt; 目录成员关系校验本进程线程，避免逐次读取 status。
- 预先保存属性区、本进程 mem 的 device/inode；保留 FD 复用、文件偏移与权限的内核语义。
- libc 与直接 syscall 共用不可变 BrokerSnapshot；普通文件经元数据检查立即返回。
- iovec 描述符复制调用 raw process_vm_readv，避免代理线程进入包含分配和动态符号解析的公共包装器。
- 自身 mem 读取按安装的相反顺序还原模块代码视图，补接 nativecompat 已确认的 ART 入口视图；后来的第三方修改保留。

六项策略、分类开关、固定参数和应用作用域语义未改变。

## 修复后的检查

四种 ABI 构建和签名已完成。候选模块为 [AppStateShield-xianyu-broker.apk](AppStateShield-xianyu-broker.apk)。

修复后 user10 PID 26984 从清数据后的隐私同意进入通知权限对话框；拒绝通知后到可选登录页，关闭登录页后到 MainActivity。首次观察窗口超过 62 秒，后续仍为同一主进程，UI 导出得到正常首页资源 ID。所有新 ANR 文件核对后仍属于旧 PID 18969；未出现 PID 26984 的新增 ANR。模块记录六项全开、native compatibility ready、设备 native 层初始化成功。未登录，也未验证登录后的签名请求。

[NativeBrokerTest](native-broker-20261119-results.json) 已通过真实 seccomp 下的 raw 描述符复制/EFAULT、readv/preadv、线程、fork 子进程原值、dup 偏移、EOF、EBADF、普通管道及关闭后原值。它使用生产头文件的独立可执行夹具；已有线程与 APK 内属性区另由下面的集成检查验证。

[APK 集成结果](xianyu-broker-apk-results.json) 共 6 项通过：原值、长参数开启、短参数更新、字段取消选择、总开关关闭、10 个向量/错误/偏移断言。同一 PID 与启用代理前已存在的工作线程保持不变，属性区的 libc/raw read 与 mmap、缓存 FD、代码读取视图均符合预期。此次 keys=false，没有执行证明密钥检查。执行器最初少列了正式验证器的 APK 名称，导致来源字段为空；随后核对已有构建时快照、当前源码、原 APK 哈希与全部 APK 内容，为本轮记录补齐来源元数据，没有重跑应用检查。case 的耗时只记录断言/写报告步骤，不当作完整探测耗时。

[SELinux 与六项组合结果](selinux-xianyu-broker-results.json) 共 83 个记录通过，包含 64 个不同开关组合、真实 Permissive/Enforcing 对照、真实 UI 策略保存、独立 UID、策略默认/隔离、HTTPS、10 次冷启动、3 组原生截图/普通文件读数及恢复。全部 64 组合同时开启机器档案，确认 deviceSyscallView=1；保留 direct syscall、读取权限和普通 FD 的原语义。夹具中的截图文件不表示真实 SystemUI 截图事件通过。

[交付物核对](xianyu-broker-artifact-checks.json) 确认四个 APK 的内容与本次 build-inputs.json 一致，各自包含四种 ABI。正式验证器没有 src/debug 的 OEM 类、IncrementalProbeActivity、CapabilityProbeActivity 和对应 JNI 库。初次打包检查误把正式诊断入口 FixtureActivity 当作 debug 类，已改为核对实际 src/debug 类描述符；这是检查器断言错误，不是 APK 缺陷。模块及正式验证器使用原外部证书，SHA-256 为 e5e7f749fd8d02ccb8b19439bf0ac56800801ab544ef2b8d0968cca036956dfe。四种 ABI 的编译不等同于四种 ABI 的运行验证，本轮实际运行 ARM64/API36。

| 文件 | SHA-256 |
|---|---|
| AppStateShield-xianyu-broker.apk | 57c09d81ecd464541a58a9d782d180c0d04804b26fc8e9dd2e9d4c9f69e8305c |
| AppStateVerifier-xianyu-broker.apk | 970112c6beaf4656eab0a867f7bb2f92cffec8bd50a46105ff6a16d4b743da50 |

## 手机与环境恢复

手机重新连接后，只读核对 user999 的档案与用户此次重建的快照完全一致。第一次沿用覆盖安装授权执行 adb install，系统返回 INSTALL_FAILED_ABORTED: User rejected permissions。[第一次安装记录](vivo-xianyu-broker-install-20261119.json) 保留该次拒绝与当时手机仍为原模块的事实，没有绕过拒绝或清除数据。

用户随后明确要求“再试”，第二次安装成功。[真机验证记录](vivo-xianyu-broker-20261120.json) 确认安装哈希为 57c09d81…，闲鱼实际映射的模块 APK 就是该安装文件。第一次安装后的 PID 22823 虽进入首页，但日志为 Policy loaded=false，没有设备 native 初始化；该次不算机器伪装原配置通过。覆盖安装后分身模块处于 stopped 状态，读取配置抛 IllegalArgumentException。打开一次分身模块 SettingsActivity，由现有 onCreate → PolicyVisibility.restore 恢复读取可见性，没有保存或修改设置。

随后通过桌面入口冷启动 user999 的闲鱼，PID 31554 在 13 次采样、67.18 秒窗口内始终存在，exit-info 无该 PID 的新增退出；真实 UI 为 user999 MainActivity，首页资源可导出。该 PID 记录 Policy loaded=true、六项方法全开、native compatibility ready=1、DeviceProfile native ready hooks=3 objects=1。机器档案仍为总开关开启、标识符开启、网络 no_sim，其余分类关闭，46 项选择及固定值未改。主用户和分身模块的全部偏好文件内容、属主/权限、revision，所有 Vector 模块状态与作用域逐项核对一致。没有清除闲鱼数据、登录账号或执行证明请求。设置页首次等待判断比选择器切换更早返回，随后同一次启动已正确进入 SettingsActivity；补充了有上限的页面就绪等待，这个执行器错误不作为应用故障。

[最终模拟器恢复](xianyu-broker-emulator-restoration.json) 确认先恢复原 SELinux 模式与临时服务/夹具，ADB 返回 UID 2000，然后停止 emulator-5584，把原磁盘重新放回活动 AVD。逐文件 SHA-256、大小、权限、目录与符号链接清单和 original.json 一致，ramdisk 哈希一致；原 APK、数据、授权、设置及作用域由完整磁盘恢复。测试磁盘另存于仓库外，没有覆盖之前的原始快照或测试记录。emulator-5594 未操作。

上述模拟器首次初始化与 vivo 原配置冷启动只保留为本阶段的局部观察。该旧候选当时尚未通过用户四步，真机没有在本阶段重做清数据，无法据此证明故障已修复。后续自然 ART 栈、旧候选完整四步失败与新候选首页响应见 [最新真机验收](XIANYU-VIVO-FOUR-STEP-20261120.md)。长期失败频率与登录后请求仍未确认；源码与 APK 未提交或推送。
