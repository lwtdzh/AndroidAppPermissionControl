# vivo 闲鱼分身：最新候选四步首次启动验收通过

**最新结果：2026-11-20 14:52，SHA-256 为 5bffe4dbae6becf2c49f5918eb495c6b9123d5c88fadce0d02c49160733493e5 的候选在这台 vivo 上完整走完四步，实际同意协议后进入正式首页，首页“同城”导航触发正常位置权限请求。** 首次主进程 PID 27337 / user999 保持不变，截至最后只读核对没有该 PID 的退出事件。本候选的 64 组合、开启/更新/关闭与相关原生检查已通过，见[本次结果](XIANYU-CALLER-READ-FIX-20261120.md)。下文保留此前失败与定位过程。

**历史失败：2026-11-20 11:37，旧候选 APK 在 vivo V2419A 上完整复现了用户报告的问题，该候选未通过。** 当时已经执行清分身数据、分身模块作用域关闭保存再开启保存、删除并重建分身配置、重新启动并同意许可协议。闲鱼停在 InitActivity，随后主进程及辅助进程因 ANR 退出。

安装的模块 SHA-256 为 57c09d81ecd464541a58a9d782d180c0d04804b26fc8e9dd2e9d4c9f69e8305c。闲鱼 base/split 与前轮复制的原始签名文件相同。目标为 user999 / UID 99910400，分身模块 UID 为 99910469。本轮没有新建或安装 APK。

| 步骤 | 本轮实际证据 |
|---|---|
| 清分身数据 | 仅对 user999 的 com.taobao.idlefish 执行 pm clear，返回 Success |
| 关闭保存，再开启保存 | 打开手机现有 Vector 快捷方式，选择“应用分身”侧模块；取消闲鱼并点击“应用”，读回作用域已移除；重新勾选并“应用”，读回恢复，其他作用域不变 |
| 删除重建配置 | 从 Vector 打开 user999 SettingsActivity；真实删除定制并读回两个文档中的闲鱼项均已删除；重新添加、开启机器总开关与设备标识、选择 no_sim、保存；六项状态开关均为开启并保存 |
| 同意协议后的首次启动 | user999 PID 8376 显示首次协议并同意；轻量时间线仍停在 InitActivity，随后退出；没有到可操作首页 |

Vector 在这台手机使用注入 com.android.shell 的管理界面，其现有快捷方式指向 BugreportWarningActivity，并非独立安装的 manager APK。此次使用它的“应用分身”页，所选模块和配套设置均确认属于 user999。模拟器中的独立 manager APK 行为不能替代这项证据。

新档案为 enabled=true、idsEnabled=true、networkMode=no_sim，其余分类关闭，字段选择为默认 46/47。主进程日志记录六项策略加载成功、ART code views=8、native compatibility ready=1、DeviceProfile native ready hooks=3 objects=1。辅助进程也加载了这些入口；配置加载成功仍不能代替各个 API 返回值的验证。

系统记录 PID 8376 在 11:37:31 因 ANR 退出，PID 8761 在 11:37:42 因 ANR 退出。对应自然生成的 ANR 文件为 anr_2026-11-20-11-37-15-287 和 anr_2026-11-20-11-37-31-234。首次启动观察只查询进程和前台 Activity，没有 ptrace、debuggerd 或逐线程读取。

这轮自然 ANR 未能取得目标的 ART 栈，系统栈采集超时。等待记录确认主线程持续处于 futex_wait_queue；11:37:25 有八个线程等待 seccomp，11:37:28 代理线程回到 seccomp_notify_ioctl。它们说明读调用经过代理，尚不足以证明代理永久死锁或确认具体持锁者。

此前读取了用户 10:59 那轮自然 ANR，也存在主进程/辅助进程启动超时和栈采集超时。随后保留当前数据启动，PID 17504 能从待同意协议走到通知权限页；这次只用于对照，不能算完整流程通过。该对照中的旧采集器因逐线程启动 cat 开销过大而停止，采集耗时不能当启动耗时。

该轮之后抓取完整清数据场景中的有界原生线程证据，定位主线程等待、SecurityGuard 工作线程与系统调用代理的具体位置，结果见后文。诊断干预单独标记，受干预启动不替代最终四步验收。此前的模拟器成功和真机局部启动保留原归属。

手机模块设置快照、作用域读回、完整流程界面记录、时间线、模块事件与自然等待记录均保存在仓库外的私有目录。此前手机快照未覆盖用户的新设置；源码与 APK 未提交或推送。

## 后续原生采样与候选版

再次只清 user999 闲鱼数据并同意协议后，PID 10102 在协议后 2、8、15 秒接受有界 ptrace 采样，每次分别为 37、56、59 毫秒。此轮带有诊断干预，没有重新走作用域与删除配置两步，不作四步验收。主线程初期在 ART Thread::Park / Unsafe.park；这只能证明它在等待任务，尚未取得对应 Java 调用方。

协议后 8、15 秒，代理 TID 10157 位于 libunwindstack 信号处理函数的 ThreadEntry::Wait，原始被打断位置仍在 libc ioctl。Signal Catcher 同时位于内存读取的 seccomp 等待。读取本机 libunwindstack 与 libart 的代码确认：AndroidLocalUnwinder::InternalUnwind 给被采集线程发送信号 33；处理函数在复制寄存器并唤醒采集方后，等待采集方释放它。暂停代理后，采集方读取自身内存又请求该代理，形成循环等待。该证据说明栈采集本身为何卡住，不能单独证明闲鱼首次初始化的全部问题。

候选版只为代理线程增加 ready 前的 raw rt_sigprocmask，屏蔽 Bionic 保留的信号 33；应用线程掩码不变。四 ABI 构建通过，签名候选为 [AppStateShield-xianyu-backtrace.apk](AppStateShield-xianyu-backtrace.apk)，SHA-256 为 4ba48d3d995cd38b19ad5978f378995839c0a02cc5af5217226fab1a4933e4f9。对应代理线程的信号式栈采集会走采集方的超时处理。

专用 emulator-5584 的独立代理测试通过了原读取、iovec、FD、线程/子进程和关闭对照；新增对照确认代理收到信号 33 后仍能服务，调用线程仍能收到信号。见 [原生结果](native-broker-backtrace-20261120-results.json)。候选 APK 的同进程开启与更新通过，Java 序列号和三条 native 属性读取匹配保存值。关闭后 native 属性及 Build.SERIAL 恢复；Build.getSerial 返回 TimeoutException，关闭用例仍记为失败，待定位。见 [集成结果](xianyu-backtrace-integration-20261120.json)。没有复用旧 APK 的 64 组合来宣称本候选已通过。

手机在这次更新期间断开 USB。断开前最后一次核对仍为旧 SHA-256，当时未确认候选安装完成、配置保留与真机完整四步；重连后的结果见后文。新增代理测试通过不代表闲鱼已修复。

11:59 已停止专用模拟器并恢复完整原始磁盘；每个文件、权限和 ramdisk 哈希均匹配此前快照，测试磁盘另存仓库外，emulator-5594 未操作。见 [恢复记录](xianyu-backtrace-emulator-restoration.json)。修正测试按钮后重新运行根构建成功，当前源码与 build-inputs 匹配，候选 APK 内容与最终构建匹配；前述部分运行结果仍保留原编译快照归属。

## 手机重连后的实际页面

14:17 重连读回确认，手机已安装 SHA-256 为 4ba48d3d995cd38b19ad5978f378995839c0a02cc5af5217226fab1a4933e4f9 的候选。说明此前断开期间更新后来完成了。主用户及分身的两份配置文档、所有作用域及文件所有者均与更新前快照一致；后来启动的同字节更新命令等待超时后停止，未把它当新的成功安装证据。

只清 user999 闲鱼数据后，真实协议页在前台。14:19 点击“同意”，进入通知权限页；拒绝通知并关闭可选登录引导后，14:20:06 前台为 user999 的 maincontainer.activity.MainActivity，UI 中出现首页、同城、搜索等正式入口。该诊断轮有原生采样，且未重新走作用域关闭/开启及删除重建配置，不作为完整四步通过。随后的完整四步结果见后文。

验收依据是**点击“同意”后进入可操作的正式首页**。停在 splash screen，或者最后闪退，均不能通过。采样时间只用于诊断及补充记录，等待某个固定秒数、进程存活或只出现协议页均不是通过条件。

## 14:27 完整四步仍失败，已取得初始化调用链

候选 4ba48d3d… 重新完整走了四步：14:22:30 清 user999 闲鱼；Vector“应用分身”侧取消闲鱼并保存、读回移除，再选中并保存、读回恢复；删除定制并确认两份文档中的闲鱼项消失，随后通过 UI 重建 machine=true、idsEnabled=true、networkMode=no_sim、六方法全开，档案 revision 为 1795156004685；14:27:29 发起首次启动，协议页真实出现并点击“同意”。

同意后的 UI 已到通知权限页，但首次主进程 PID 4392 在 14:27:59 被系统以 ANR 结束，未到可操作首页。后来重启的进程不替代本轮首次启动结果。点击后读取 UI 时正处于页面切换，uiautomator 返回 null root；该失败发生在点击完成之后，保留命令日志与随后通知权限页作为实际操作证据，未重新点击或启动来补写成功。

系统自然产生的 /data/anr/trace_00 包含 PID 4392、时间 14:27:42 的 ART 栈。主线程调用链为 InitPrivacyDialog 同意回调 → InitActivity.enterAppAfterPrivacyAgree → FishNewBlink.prepare → BlinkNewEngine.ParallelSyncRun.execRun → ConditionObject.await。登录等任务等待 SecurityGuard 初始化锁；持锁 ART TID 66 正在 SecurityGuardInitConfig.initSecurity → JNICLibrary.doCommandNative → libsgmainso → 模块 libselinuxstate 的 h_fread → enforceFd → raw readlinkat。APK 的 library offset 与当前未剥离库符号逐一匹配，三条模块地址解析为上述函数。

随后 fread1 诊断轮只清数据并同意，接受有界原生采样，单独标记非验收。2 秒采样经过 libc FILE refill → 模块 h_read → read，8 秒采样仍在 SELinux h_fread 的 enforceFd/readlinkat；代理没有停在信号处理函数。该路径对每次已缓冲的 fread 都额外解析一次 FD 路径。随后验证修改：read 已安装或已注册组合过滤时，让 Bionic 的 FILE refill 在读取时过滤字节，避免重复包装 fread/fgets；read 未能覆盖时保留原包装。该阶段尚不能宣称修复，后续完整四步与 API 结果见下文。

## 14:38 第二轮四步仍失败，继续消除重复代理

取消重复 FILE 包装的候选 SHA-256 为 e729c5ab272747830640a4137806878a496f5ee1d2d24e86fb19404b6d489a46。手机安装后两用户的文档和作用域均保留。14:36:42 清 user999 闲鱼，真实作用域关闭保存/开启保存，再删除重建定制；新 revision 为 1795156701939，machine、ids、no_sim、六项保持预期。14:38:46.804 点击“同意”；仍在首次主进程 PID 17036 上发生 ANR，于 14:39:07.542 退出，没有进入可操作首页。该轮无 ptrace。系统新 trace_02 的 ART TID 66 仍为 SecurityGuardInitConfig.initSecurity，native 路径已经变为 libc fread → FILE refill → 模块 read 包装器。

专用模拟器的独立代理吞吐夹具读取 /dev/zero：10 万次 4 KiB，原路径约 28–33 毫秒，代理路径约 2.7–5.5 秒。这是代理开销对照，不是闲鱼读取次数或启动耗时。曾试将文件元数据判断前移，交替对照未见稳定改善，已撤掉该试验，没有安装该候选到手机。

随后进一步调整已接管的 read/__read_chk：完成截图路径检查后，经设备层 raw KernelRead 在调用线程读取真实 FD，随后继续应用同一机器快照和 SELinux 过滤；应用自己的直接系统调用仍走原代理。四 ABI 构建、签名和独立代理契约检查通过。

新候选的专用模拟器联测初期遇到真实基线异常：TUN 存在、VPN service 存活，但 Connectivity 的 VPN agent 消失，未注入验证器读到未连接；两次失败原样保留。保存现场、恢复 Enforcing 并仅重启专用模拟器后，重新建立实际 CONNECTED VPN agent，原断言的六个 Permissive/Enforcing 定向用例全部通过，机器档案开启、ids=true、network=no_sim。没有把接口存在当连接成功，也没有放宽 VPN 断言。该阶段手机尚未完成新候选四步，随后实际结果见下文。

## 14:52 第三轮完整四步到达正式首页

安装的 caller-read 候选 SHA-256 为 5bffe4dbae6becf2c49f5918eb495c6b9123d5c88fadce0d02c49160733493e5。14:50:29 清 user999 闲鱼；在原 Vector“应用分身”作用域页关闭并保存、读回，再开启并保存、读回；从该页打开 u999 配套设置，删除定制并确认两份文档中的闲鱼项均删除。通过 UI 重新添加，保存机器总开关、设备标识、no_sim、默认字段选择与六项全开，新 revision 为 1795157526515。主用户文档、其他分身条目、所有作用域及文件所有者均核对保留。

14:52:36.123 实际点击“同意”。关闭可选通知提示、登录引导后，14:53:03 前台为 user999 MainActivity，首页包含正式内容与导航。点击“同城”后出现该闲鱼分身的位置权限请求；拒绝后正常出现权限说明对话框。首次 PID 一直为 27337，没有由 ANR 自动重启的替代进程，整个验收无 ptrace。

曾点击首页搜索栏，但没有观察到搜索页，因此不将这项操作计作响应证据。同城权限请求是实际响应证据。尝试关闭说明并返回首页时，手机前台出现另一个 MyFish 安装提示；没有确认或取消这项外部安装，也没有把它记成闲鱼退出。此前正式首页和导航响应证据已保存。完整结果见 [真机记录](vivo-xianyu-caller1-20261120.json)。

模块日志确认本轮策略加载成功、六方法开启、ART 代码视图与设备 native 入口加载。各 API 读数由本候选的模拟器实际基线与同进程集成检查分别证明，日志不代替 API 验证。最新真机四步首次启动、64 组合、相关原生文件与机器档案开启/更新/关闭均通过；完整结果和恢复记录见[本次结果](XIANYU-CALLER-READ-FIX-20261120.md)，未提交或推送。
