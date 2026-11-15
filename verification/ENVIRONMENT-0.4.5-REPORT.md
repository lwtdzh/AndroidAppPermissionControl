# AppStateShield 0.4.5 调研、修复与验证

已完成公开资料和源码调研，保存 32 类环境检测与本应用对照，归档 9 个项目的固定提交源码及 Vector 2.2、AOSP 版本依据。调研主报告与原文索引在交付包 research 目录；每份源码保留许可证、来源及 SHA-256。Momo 没有可核对完整源码，reveny 仓库没有对应 native 实现，均明确标注；没有冒充已经解析其算法。

## 已修复

1. 完整指纹同步 Build.ID、TYPE、TAGS 及各分区编译属性。真实预设保留自己的分区差异；手工指纹按输入推导，不猜固件值。指纹字段关闭后关联值恢复。
2. 验证器状态接口固定包名与发布签名；同名状态类的其他包，以及允许包的其他签名都不会收到模块状态。
3. 设备伪装从未开启时不安装设备 Java Hook；首次开启时安装，前台轮询与保存通知继续支持更新，关闭恢复，避免重复安装。
4. 设置页按草稿提示不一致字段、跨 Android 大版本、隐藏传感器和 SIM 对运营商一键登录的影响；保存/丢弃通过真实 UI 核对。
5. 可选容量按真实占比同步总量、可用/剩余量和块数。StatFs 和普通 File 按设备号识别数据文件系统，系统分区保留原值。实际内存和磁盘不变。
6. 验证器新增真实读取的编译元数据、类型化属性和内存/数据分区容量，结果来源与模块配置分开。

实现和 32 项处理状态详见 docs/ENVIRONMENT-0.4.5.md。源码压缩包包含这些文档及测试脚本。

## 本次实际检查

PASS 241 metadata, gates, warnings and capacity assertions

PASS 22 typed property number, overflow and boolean assertions

Android 16 / ARM64 / Vector / 专用 ScreenshotShield_API36：10 项定向检查通过，合计 58.6 秒。每项记录本次 APK、构建输入、开始时间和耗时。开启/自定义更新/关闭检查确认阶段内 PID 不变。单独冷启动用于共享入口和身份反例，不把不同阶段的 PID 写成一直相同。

| 用例 | 结果 | 耗时 |
|---|---|---|
| E01-never-enabled-baseline | 通过 | 2.276 秒 |
| E02-first-enable-ui-and-reads | 通过 | 14.172 秒 |
| E03-warning-draft-discard | 通过 | 25.973 秒 |
| E04-live-custom-metadata-capacity | 通过 | 3.41 秒 |
| E05-field-and-master-restore | 通过 | 5.965 秒 |
| E06-authentic-sample-accepted | 通过 | 1.187 秒 |
| E07-foreign-same-class-rejected | 通过 | 1.329 秒 |
| E08-wrong-signer-rejected | 通过 | 1.796 秒 |
| E09-shared-debug-selinux | 通过 | 1.075 秒 |
| E10-all-methods-startup | 通过 | 1.413 秒 |

根与五个分区的 ID/TYPE/TAGS 通过 Java/native 对照。原系统缺少某属性时 native find 没有 prop_info，旧 read/callback 仍可能没有数据；没有把缺失值当作完整虚拟属性区成功。指纹的 get/read/callback、值缓冲区及哨兵在相关启用/更新/共享入口中检查；0.4.4 的不变 sanitizer 边界矩阵没有重复执行。

类型化属性确认密度 getInt/getLong 与设置一致，未知属性保留默认值。容量确认 available ≤ free ≤ total，字节与块数一致，File 总量与 StatFs 一致，系统分区保留；普通文件读写正常。内存确认可用量和阈值不大于总量，关闭时恢复总量。

首轮真实检查发现密度的字符串属性已替换，getInt/getLong 仍返回缺省值 -17。已补 getInt/getLong/getBoolean 的选定属性适配，保持默认值、整数溢出和布尔文本语义。新增 22 条类型化解析检查单独执行，没有重复前面已通过的 241 条纯逻辑检查。首轮 API 27 签名接口的 lint 错误也已增加版本守卫修复。执行器初次遇到未安装包的 pm path 非零返回，已改用实际安装列表；原快照保留，未从头重建。

错误签名反例首轮在卸载/重装目标包后没有获得设备适配读数，不能当作签名校验成功。保留其他 9 项通过结果，仅对这一项重建作用域绑定并冷启动；此后既能读取指定伪装编号，又没有模块状态上报，反例才判为通过。失败和续跑日志均保留。

身份反例使用同名状态类：错误包与错误签名不收到上报，但仍读到专门设置的伪装编译编号，确认模块确实已进入该进程。反例属于测试包，不在正式交付安装包中。

四 ABI 编译齐全，正式 APK 排除 debug 厂商夹具，签名沿用原身份。Lint 无错误；模块 23 项警告，验证器 79 项警告。API 27 上不提供仅 API 28+ 验证器可用的状态上报；API 27/其他 ABI 未做运行验证。

0.4.4 的 64 组合保留原哈希与原报告。Methods、策略和共享 native 实现按旧源码归档逐字节对照未变；本次新增共享 debug/SELinux 和六项全开启动核对。旧检测器没有这次新增读数，旧记录没有改标为 0.4.5，也没有升级为程序化跨 APK 复用。

## 未完成的能力与登录结论

没有连接 vivo，本次没有安装到真机，也没有执行淘宝/拼多多真实登录。当前结果不能证明这两款应用恢复登录。

Vector 2.2 排除隔离 UID/AppZygote；原始属性区/serial、外部 exec、任意内联 SVC、ART 根引用、代码与磁盘对照、CPU/GPU/HAL/内核及 TEE 证明仍不完全受本模块控制。完整硬件互换、服务端账号/行为关联也未实现。调研把这些入口逐项列出，未用重命名或清空列表冒充修复。

模拟无 SIM 或模拟有 SIM 不创建真实运营商通道，运营商一键登录可能失败；密码/短信登录也由真实服务端决定。跨 Android 大版本预设仍有实际 API/内核矛盾。首次开启前已缓存的 StatFs 对象、静态字段内联和应用缓存需冷启动。

## 恢复与安装

专用模拟器原 APK、数据、设置、作用域、模式及应用语言已恢复；身份反例包已移除。ADB 已解除 root，专用模拟器关闭。未操作无关 emulator-5594。手机尚未连接，交付两个同签名 APK；安装后目标应用需彻底关闭再打开。

| 安装包 | SHA-256 |
|---|---|
| AppStateShield-0.4.5.apk | 2eb2c547df6e3d8e3d34552139d581d25733dd7acb291cd6f7442e6cc95db693 |
| AppStateVerifier-0.4.5.apk | 82d232f3fc680f23f21957ba0174de4dd40ce1aeeb5e44f07e66cb7054d17471 |
