# 闲鱼分身首次启动：vivo 四步验收通过

2026-11-20，caller-read 候选已在用户授权的 vivo V2419A / user999 上完整走完四步。实际点击许可协议“同意”后，首次主进程进入正式首页；点击“同城”出现该分身的位置权限请求，拒绝后正常显示权限说明。没有使用 ptrace，没有用 ANR 后重启的进程替代首次启动。手机保留这一版本与此次通过真实 UI 重建的配置。

## 四步的实际结果

| 操作 | 证据 |
|---|---|
| 清除闲鱼分身数据 | 14:50:29，仅清 user999 / UID 99910400 的闲鱼，返回 Success |
| 分身侧 Vector 作用域关闭保存，再开启保存 | 在手机现有“应用分身”页实际操作，分别读回关闭、开启；其他作用域保留 |
| 删除并重建定制 | 实际删除，确认策略与机器档案的闲鱼项均消失；通过 UI 重新创建并保存，机器总开关、设备标识、no_sim 与六项状态屏蔽全开；revision 1795157526515 |
| 同意协议并进入正式页面 | 14:52:36.123 点击“同意”；关闭可选提示后，14:53:03 为 user999 MainActivity，首页导航有实际响应；首次 PID 始终为 27337 |

这两个时间包含页面检查与可选提示操作，不作为单独测得的初始化耗时。验收依据是实际进入可操作的正式首页。点击搜索栏没有观察到搜索页，未将其计为响应证据。

[完整真机记录](vivo-xianyu-caller1-20261120.json)记录实际 APK、分身 UID、策略加载和 native 入口；[最后只读核对](vivo-xianyu-caller-read-final-preservation.json)确认模块安装字节、所有自身作用域、主用户与分身配置及属主仍匹配验收状态，首次 PID 没有退出记录。没有用旧手机快照覆盖用户的新配置。

## 定位与修改

旧候选完整四步仍失败。系统自然产生的 ART 栈确认：许可协议同意回调 → InitActivity.enterAppAfterPrivacyAgree → FishNewBlink.prepare → ParallelSyncRun.await。启动任务在等 SecurityGuard 初始化锁；持锁线程经 SecurityGuardInitConfig.initSecurity → JNICLibrary → libsgmainso，进入模块的 FILE/read 路径。旧轮次、地址解析与诊断干预分别保存在[定位过程](XIANYU-VIVO-FOUR-STEP-20261120.md)。

本次针对这条路径减少重复开销：

- SELinux 已覆盖 Bionic FILE refill 的 read 时，不再额外包装每次 fread/fgets；未覆盖时保留原包装。
- screenshot 已接管的 read/__read_chk 完成 FD 检查后，在调用线程通过设备层 KernelRead 读取真实 FD，再应用同一机器快照与 SELinux 过滤，减少一次代理等待。超出容量仍调用原 fortify 函数；应用直接 syscall 和 mmap 保留原代理。
- 保留此前已验证的代理信号 33 隔离，避免栈采集暂停代理后，采集方又等待代理读取内存。

独立 10 万次 4 KiB 读取对照中，原路径约 28–33 毫秒，代理路径约 2.7–5.5 秒。该数字说明代理开销，不代表闲鱼实际读取次数或初始化耗时。六方法、机器分类开关、字段选择与 Vector 作用域语义保持原规则。

## 本候选的验证

| 检查 | 结果 |
|---|---|
| vivo 完整四步 | 正式首页与同城导航响应，通过 |
| 同 PID 序列号开启、更新、关闭 | 4 项通过，PID 20703；Build.getSerial、Build.SERIAL 与三条 native 属性读取恢复原值 |
| 机器、设备标识、no_sim 与六方法联测 | 64 个不同组合全部通过；机器档案 revision 相同，deviceSyscallView=1 |
| SELinux、普通文件、方法隔离与策略 | 共 81 个当前记录通过，包括真实 Permissive/Enforcing、独立 UID、默认/未来方法、HTTPS、Provider 隔离和 3 组原生文件检查 |
| APK 属性区与代码读取 | 6 项通过；开启、短参数更新、取消选择、关闭保持 PID 3961 / 已有工作线程 TID 3992；libc/raw 读取、mmap、缓存 FD 与普通操作均符合断言 |
| 代理契约 | 12 个契约通过，包括 FD 复用、iovec、EFAULT、偏移、EOF、EBADF、管道、fork、信号隔离和关闭后原值 |
| 构建与打包 | 当前源码和 APK 内容匹配构建输入；四 ABI 与签名通过，正式验证器排除 debug 类和 JNI 夹具 |

运行结果分别为[序列号集成](xianyu-caller-read-integration-20261120.json)、[81 项与组合](selinux-xianyu-caller-read-results.json)、[APK 文件视图](xianyu-caller-read-apk-results.json)、[代理契约](native-broker-caller-read-20261120-results.json)及[交付物核对](xianyu-caller-read-artifact-checks.json)。没有复用旧候选的 64 组合来宣称本候选通过；中断后保留同 APK 已通过的组合。

序列号集成含真实 UI 编辑与保存，总耗时 30.063 秒；64 个组合的探测用例耗时合计 40.355 秒，不包含全部配置、作用域和 UI 操作。原 I07 执行器的 durationSeconds 只计断言写报告步骤，不当作原生探测耗时。

本轮曾遇到两次未注入 VPN 基线失败，保存现场后恢复实际 CONNECTED agent，原断言通过。另一次独立 UID 检查中，A/B 调试包默认 Android 调试证书不符合 VerifierIdentity；模块实际加载且 SELinux 读取已过滤，但私有标记未启用。用原外部身份重新签署临时包后通过，未修改身份校验或生产 APK。更换 VPN 宿主包 UID 后，系统 agent 登记未完成；已保存该失败及停止/启动对照，只重启专用模拟器一次，再确认实际连接、复测原断言并继续。未确认这次系统登记异常的内部原因，不将它归因为模块修复。上述失败保留在 previousRuns 和私有现场中。

## 文件与适用范围

| 文件 | SHA-256 |
|---|---|
| [AppStateShield-xianyu-caller-read.apk](AppStateShield-xianyu-caller-read.apk) | 5bffe4dbae6becf2c49f5918eb495c6b9123d5c88fadce0d02c49160733493e5 |
| [AppStateVerifier-xianyu-caller-read.apk](AppStateVerifier-xianyu-caller-read.apk) | 970112c6beaf4656eab0a867f7bb2f92cffec8bd50a46105ff6a16d4b743da50 |

正式模块与验证器保留原外部签名。A/B 仅是专用模拟器里的临时测试目标，正常使用不需要安装。原生运行检查实际使用 ARM64 / API36 专用模拟器；四 ABI 编译不等于四 ABI 运行验证。模拟器结论不外推为其他厂商 ROM；此次 vivo 四步也不代表登录后请求或长期稳定性已验证。

直接 syscall、未注入子进程和保留的外部入口仍有各自限制；不完整 fread、EOF、原读取错误及普通 FD 的断言未放宽。构造截图文件不等于真实 SystemUI 截图事件。本次文件读取修改不改变真实系统 SELinux 状态；测试只在专用模拟器切换实际基线，结束时恢复原模式。

专用模拟器已先恢复原 Enforcing 模式并正常关闭。15:11 完整原盘已放回活动 AVD，逐文件哈希、大小、权限、目录与符号链接均匹配 original.json，ramdisk 哈希一致；原 APK、数据、作用域、授权、设置与服务由完整磁盘恢复。测试盘另存仓库外，emulator-5594 未操作，见[恢复记录](xianyu-caller-read-emulator-restoration.json)。手机保留验收后的新配置；源码与 APK 未提交或推送。人工重现步骤见[测试手册](../docs/TEST-MANUAL.md#闲鱼分身清数据后的首次启动)。
