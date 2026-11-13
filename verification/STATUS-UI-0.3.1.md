# AppStateShield / AppStateVerifier 0.3.1 测试与安装记录

2026-11-13。两个同签名 APK 已升级安装到 vivo V2419A / Android 16；安装后的完整 SHA-256 与模拟器测试 APK 一致。原应用策略、Vector 模块状态/作用域和系统 SELinux 模式保持原样。

## 使用

从 Vector 打开应用状态屏蔽设置，顶部“显示应用图标”默认关闭。开启后桌面入口打开同一设置页，Android 用户各自保存选择，覆盖安装保留。分身工具能否提供克隆仍取决于该工具的支持；本次验证了入口发现及用户隔离，未操作用户手机的分身工具。

验证器首页保留传统日志与读取检查，并增加每 2 秒刷新的 VPN、代理、开发者选项、USB/无线调试、SELinux 信息条。它展示应用观察到的值，注入模块时可能经过屏蔽。

截图会话计数按文件/图片身份和 2 秒窗口合并估算。实际两次 SystemUI 截图各产生官方/Binder 两条信号，会话累计两次。旋转、后台返回、重启监听、清空日志保留会话次数；结束页面或冷启动重新计数，仅首页前台期间计数。

## 实际检查

专用 ScreenshotShield_API36 / emulator-5584 / ARM64 / API36；四 ABI 构建和两个 release lint 均通过，lint 错误为 0。11 个 JVM 断言检查多入口关联、快速截图、不同文件/图片 ID、匿名重复事件及序列化恢复。

| 手册步骤/执行记录 | 结果 |
|---|---|
| I00-capture | 通过 |
| I01-default-off-upgrade | 通过 |
| I02-enable-open-upgrade | 通过 |
| I03-disable-vector-entry | 通过 |
| V01-observed-baseline | 通过 |
| V02-live-proxy | 通过 |
| V03-live-vpn | 通过 |
| V04-shielded-readings | 通过 |
| V05-real-screenshot-session | 通过 |
| I04-profile-isolation | 通过 |
| V06-rotation-background-clear | 通过 |
| V07-fresh-session | 通过 |
| V08-font-size | 通过 |
| V11-locales | 通过 |
| I99-restored | 通过 |

已人工查看界面截图；正常字号与 1.3 字号下信息条可读，传统诊断保留。专用测试用户、临时 VPN、测试截图已删除，原设置/作用域/APK 恢复后关闭模拟器。

## vivo 信息条

| 项目 | 读数 |
|---|---|
| vpn | VPN  未开启 |
| proxy | 网络代理  未配置 |
| developer | 开发者选项  未开启 |
| usb | USB 调试  未开启 |
| wireless | 无线调试  未开启 |
| selinux | SELinux  强制执行 |

这是当次应用读数，不代替未注入的系统检查。安装过程保留用户原配置，没有开启图标、改动作用域或切换系统 SELinux。USB 安装确认被 ROM 拦截时，使用已有 root 的包管理接口安装同一个已校验 APK，没有修改安全设置。

## 本次发现与限制

SELinux enforce 文件不可读时，Java boolean 的 false 可能来自读取失败。最终信息条改为“模式无法确认”，不会把它直接称为 Permissive；有真实文件 0/1 或肯定的 API 结果时再显示对应模式。强制执行的模拟器已验证该情况。所有 API 同时不可用的错误分支未另造系统夹具，保留手册 V10 供后续检查。

执行器修正了中英文匹配、锁定用户的入口查询、SystemUI 浮层等待及调试面板内的滚动位置。起始任务及后台返回都改用 MAIN/LAUNCHER；原组件直启的根 Intent 与桌面 Intent 不同，系统会在它上方新建页面，CLEAR_TOP 也会重建普通 Activity。修正前失败保存在测试数据 previousRuns 中。

截图次数为估算，匿名信号、延迟保存和快速连拍可能出现误差，0 次仍需看权限与真实截图基线。当前首页截图页要求 API34；较低版本沿用设备状态检查。

这次没有修改六种屏蔽 Hook。与已发布 0.3.0 比较，主模块 16 个、验证器 12 个原生库的字节完全相同。0.3.0 的 64 组合/SELinux 专项结果继续保留，本次没有重新执行整套矩阵，也未把历史结果计入本轮。

## 文件校验

AppStateShield-0.3.1.apk：1eeacdfe8cbffb4e8aca35df338c0d1846d91cb56d0afa1fbac34f9b8ac624a9
AppStateVerifier-0.3.1.apk：36d6e61cc477d0ed792ceac5112adc1b20c8d8e9eec11df6f93b6e5917617fd8
