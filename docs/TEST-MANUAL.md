# 应用状态屏蔽 0.2.0 人工测试手册

本手册用于整合版发布前验收。每条都要记录通过、失败或未验证，以及实际观察结果。失败必须修复后重新执行受影响步骤。没有真实开启基线、缺少权限或方法报错，都不能记为“屏蔽成功”。SELinux 未实现，无线调试开启基线在本次模拟器中无法保持，这两项不能由本手册推导为已支持。

测试环境为 Android 16 / API 36 / ARM64，已安装 Vector 的专用模拟器 `ScreenshotShield_API36`，序列号 `emulator-5584`。不要在有私人数据的设备上执行异常夹具。四 ABI 构建成功只证明可编译，其他系统和 ABI 仍需设备验证。

## P · 准备与安装

1. P01：从根目录构建 `:app:assembleRelease`、`:verifier:assemblePrimaryRelease`，以及 `sampleADebug`、`sampleBDebug`。确认生成一个主模块和一个正式验证器，主模块包含 shield、vpnstate、developerstate 三个 native 库的四 ABI。签名使用 `scripts/sign-apk.py` 和既有仓库外签名。
2. P02：启动 `scripts/start-emulator.sh -no-window`，将输出重定向到本机私有文件。确认 AVD 名称和序列号。ADB 命令始终带 `-s emulator-5584`。必要时 `adb -s emulator-5584 root`，不要操作其他模拟器或 vivo。
3. P03：安装测试 APK、修改任何设置前，执行 `python3 scripts/integration-test.py capture`。它以只读方式备份模块启用状态、作用域、目标应用授权、开发者/USB/无线调试、飞行模式、隐藏 API 策略、无障碍和通知服务、自动旋转、模块定制与应用语言；两个本机快照文件权限为 600，已被 git 忽略。保存测试前的截图 MediaStore ID，结束时只删除新增测试图片。已有快照时拒绝覆盖；上一次清理完成后，先将快照移入本机归档再开始新一轮。已有 VPN 时停止测试，不覆盖它。
4. P04：安装签名 APK。A 为主验证器 `io.github.lwtdzh.screenshotdetector`，B 为 `.samplea`，C 为 `.sampleb.screenshot`。C 的测试包名以 `.screenshot` 结尾，用于沿用截图服务的发送方判断，实际发布命名测试通知。B/C 是相同代码的临时测试目标，正式交付只有 A。
5. P05：打开桌面应用列表。只出现验证器，应用状态屏蔽没有桌面图标。Vector 模块列表能识别“应用状态屏蔽”，进入模块设置后标题、版本及默认说明正确。
6. P06：旧截图/VPN/开发者模块对 A/B/C 均关闭或移除作用域，避免重复注入。不要覆盖其他应用的作用域。确认模块不作用于自身。
7. P07：为 A/B/C 授予图片读取和所有文件访问；通知与无障碍测试另按相应步骤授权。记录实际权限，验证器显示无权限时该路径不能算通过。首次打开保护启用的验证页前，由未注入的 C 执行 `FixtureActivity` 的 `command=clipboard-save` 保存原剪贴板；备份只留在 C 的私有目录，不输出内容、不重复覆盖。清理阶段通过同入口的 `command=clipboard-restore` 恢复；自动 navigation 和 matrix 阶段会先完成备份。

常用命令（先将 `adb` 加入 PATH）：

```sh
adb -s emulator-5584 shell /data/adb/modules/zygisk_vector/cli --json modules ls
adb -s emulator-5584 shell /data/adb/modules/zygisk_vector/cli --json scope ls io.github.lwtdzh.appstateshield
adb -s emulator-5584 shell am start -n io.github.lwtdzh.appstateshield/.SettingsActivity
adb -s emulator-5584 shell am force-stop io.github.lwtdzh.screenshotdetector
adb -s emulator-5584 shell am start -n io.github.lwtdzh.screenshotdetector/io.github.lwtdzh.devicestateprobe.ProbeActivity
adb -s emulator-5584 shell cat /data/user/0/io.github.lwtdzh.screenshotdetector/files/result.json
```

最后两个命令用于设备状态快照。截图低层检查页面为 `io.github.lwtdzh.screenshotprobe.ProbeActivity`，结果为同目录的 `screenshot-result.json`。应用包名改变时 activity 的完整 Java 类名保持不变。

保留 VPN 夹具进程、只杀主进程时，Android 可能把旧任务顶端的 FixtureActivity 恢复到前台。执行器启动 Probe 时使用 `--activity-clear-top`，确保进入指定检查页；不能把未进入检查页导致的等待超时当网络故障。

## U · 设置页操作

每一项均通过真实设置页操作。读取配置用于核对，不能用直接编辑配置文件代替保存。独立运行自动执行器时也必须执行这些点击、输入和系统返回动作。

| 编号 | 操作 | 期望 |
|---|---|---|
| U01 | 首次打开设置 | 定制列表为空；默认全部开启；SELinux 标注待开发 |
| U02 | 点添加应用，搜索 A 的完整包名 | 能找到 A；模块自身不在列表 |
| U03 | 搜索验证器名称、部分包名、大小写变化、无匹配文字，再清空 | 名称/包名匹配一致；无匹配提示；清空恢复列表 |
| U04 | 关闭、开启“显示系统应用”，搜索 Settings | 关闭时不展示系统应用，开启后展示；不改变已保存配置 |
| U05 | 选择 A，不修改就取消 | 五个开关初始全开；回主页后仍无 A 条目 |
| U06 | 再选择 A，关闭 VPN，按系统返回 | 出现未保存提示；点继续编辑保留草稿 |
| U07 | 接 U06 点取消，再点丢弃 | A 条目不产生；再次进入五项全开 |
| U08 | 添加 A，全开状态保存 | A 仅一个条目，摘要“全部开启”；重开页面值相同 |
| U09 | 再次从添加列表选择已定制 A | 编辑现有条目，不产生重复条目 |
| U10 | 关闭 VPN、开发者选项，保存后重开 | 仅两项关闭；摘要 3/5；其余仍开 |
| U11 | 接 U10 开启 VPN、关闭截图，保存后重开 | 恰好截图和开发者选项关闭；旧值正确替换 |
| U12 | 点全部开启，再保存 | 五项全开；目标下次冷启动使用全开 |
| U13 | 点关闭已实现方法，再保存 | 五项全关；SELinux 仍为待开发，不声称已实现 |
| U14 | 修改一项，旋转横屏再竖屏 | 草稿、选择的应用、保存/取消按钮都保留，页面可滚动 |
| U15 | 在选择器搜索并开启系统筛选，旋转 | 搜索词、筛选状态保留，列表对应当前条件 |
| U16 | 编辑草稿时将页面退到后台，等 Android 完成停止并保存状态（dumpsys Activity 的 state=STOPPED、mHaveState=true），杀死后台设置进程，再从最近任务返回 | 可恢复的系统页面重建保留草稿；强行停止后重新打开只保留已保存配置 |
| U17 | 修改草稿，点恢复默认，先取消确认 | 草稿和已保存配置未变 |
| U18 | 再点恢复默认并确认 | A 条目消失；所有默认方法恢复开启；B/C 不变 |
| U19 | 添加 B/C，与 A 使用不同开关；保存 | 三个独立条目，无值串到其他应用；排序稳定 |
| U20 | B 存在定制时卸载 B，回设置；编辑并删除遗留条目；重装 B 后在 Vector 取消并重新勾选 B，冷启动验证 | 显示已卸载提示，仍可删除；重装并重新关联作用域后实际读取默认全开。Vector 2.2 可能保留旧 UID 的作用域条目，不能只看勾选状态 |
| U21 | 长包名、长名称、字体调大、横屏和手势导航下编辑 | 无遮挡/截断导致的不可操作；保存和返回均可点 |
| U22 | 切换 English、简体、繁体 HK/MO/TW、日本語后打开模块页 | 应用名、开关说明、按钮与提示使用所选语言；配置不变 |
| U23 | 连点保存、反复返回、反复选择同一应用 | 无崩溃、重复条目和丢失已保存值 |

## S · 作用域、默认策略与生效时间

1. S01：保持模块禁用但 A 在作用域内。打开设备状态页；`module.injected=false`，读到真实开启的状态。
2. S02：启用模块，将 A 移出作用域。A 即使有定制也不注入，真实状态仍可读。
3. S03：A 在作用域内，删除 A 定制。冷启动后 `injected=true`、`policyLoaded=true`，五种 ID 都在 enabled 中；未来测试方法也默认开启。
4. S04：A 创建全开定制。结果与 S03 相同，storedPolicy.custom=true、disabled=[]。
5. S05：A 五种方法全关且在作用域内。保持注入，但 enabled=[]；实际读取与无模块基线一致。
6. S06：目标 A 保持运行，在设置中改变开关并保存。回 A 时旧进程保持原策略；强行停止并重开后采用新策略。
7. S07：把 A 加入定制但不加 Vector 作用域。结果仍为无注入。再加作用域并冷启动，配置生效。
8. S08：移除 A 作用域并冷启动。定制仍在设置页保留，A 真实读取恢复。
9. S09：A 的 `attachBaseContext`、provider `onCreate`、Application `onCreate` 三阶段读取均符合相同策略。观察 lifecycle 快照，不可只看 Activity。
10. S10：从 `:vpn` 独立进程启动后读取其策略；同包不同进程一致。B/C UID 不同，互不串配置。
11. S11：重新启动模拟器，先等待系统启动完成，再由未注入 shell 确认 `wlan0` 为 UP、当前 Wi-Fi NetworkAgentInfo 带 VALIDATED；只有启动完成并不代表网络已连接。启动 C 的真实 VPN 夹具，确认 TUN 建立且普通 Wi-Fi 仍就绪，再冷启动 A/B/C。已保存配置、Vector 作用域和生效结果一致。目标读不到普通网络时保留失败快照，不反复重开直到偶然通过。

## M · 五种方法的 32 个组合

位顺序固定为截图、VPN、代理、开发者选项、USB/无线调试。1=开启，0=关闭。以下每一行都要独立操作设置页、保存、冷启动 A，并检查设备状态快照、截图读取快照及普通操作。不要只读取 enabled 标记。

```text
00000 00001 00010 00011 00100 00101 00110 00111
01000 01001 01010 01011 01100 01101 01110 01111
10000 10001 10010 10011 10100 10101 10110 10111
11000 11001 11010 11011 11100 11101 11110 11111
```

按下列规则判断每一行：

- enabled ID 必须与开关逐个相等，policyLoaded=true。
- 截图开启：截图 Java/NIO/native 读取不可用；关闭：恢复可用。普通图片始终可读。
- VPN 开启：真实 VPN 保持运行，应用的 VPN 标记、回调、Parcel 和隧道接口不可见；关闭：恢复可见。
- 代理开启：代理 metadata 不可见；关闭：恢复可见。两者真实 HTTP 代理请求都成功。
- 开发者选项开启：开发者读取为 0；关闭：真实值 1。调试开关不得随它变化。
- USB/无线调试开启：调试设置为 0，adbd/USB 属性去掉调试信息；关闭：真实 adbd 和 USB 信息恢复。无线开启未建立时只检查当前零值路径。
- airplane_mode、SDK、普通接口、网络 handle、文件 syscall/getpid/mmap/clone 控制均正常。

M33：A=10101，B=01010，C 没有定制；三者都在作用域内。依次冷启动并读取 A/B/C，确认两个相反配置和 C 的全开默认。M34：仅把 A 改成 01010，B/C 结果保持不变。M35：删除 A 定制，A 恢复全开，B 的定制保留。

## D · 开发者和调试读取路径

1. D01：打开系统的开发者选项页面，确认开发者选项与 USB 调试的真实开关开启；若已开启，无需重复关闭再开。未开启时从系统页面开启并确认。由未注入 shell 确认 `development_settings_enabled=1`、`adb_enabled=1`、`init.svc.adbd=running`。整个测试中 ADB 仍可用，实际设置不能被关闭。
2. D02：全关基线下，对三个设置分别读 Global/Secure/System，getString/getInt/getLong/getFloat、resolver.call、client.call、query、仅 value 投影、Bundle query。记录真实支持的值；报错不当零。
3. D03：只开启 developer，所有开发者读取改为 0，其余调试读取与基线一致。
4. D04：只开启 debug，USB/无线查询改为 0，developer 仍为 1。
5. D05：两者开启，三设置全零。query value/int/long/float 一致；value-only 投影列名仍仅 value；Cursor 可正常关闭。
6. D06：原生属性 get/read/read_callback 和 Java 属性读取分别核对 adbd=stopped、调试端口=-1、USB 配置不含 adb。关闭 debug 后恢复真实值。
7. D07：普通 airplane_mode、ro.build.version.sdk 与原始值一致，ADB 不断开。
8. D08：尝试建立真实无线调试开启基线并记录系统是否保持 1；若回零，写“未验证开启状态”，不可计通过。

## V · VPN 与代理读取、普通联网

1. V01：在未作用域的 C 设备状态页启动 VPN 测试（action=vpn-start）。通过系统 VPN 同意框后，从 shell ip link 确认真实 tun 接口；原网络和公网访问保持正常。夹具只路由 TEST-NET，不覆盖已有 VPN。
2. V02：A 无保护基线：vpnNetworks=1，activeVpn、parcelVpn、callbackVpn、legacyVpn、tunByName、linkTextTunnel 为真；activeNotVpn=false。Java/native 接口列表都有隧道。
3. V03：仅 VPN 开启：上述 VPN 信号隐藏，activeNotVpn=true。真实 TUN 仍存在；普通接口和网络 handle 保留。
4. V04：网络回调必须确实收到，不能把超时当 false；native listLifetimeOk/getpidOk 必须真。连续冷启动十次，确认无 native 列表释放崩溃。
5. V05：仅代理开启：proxyFixture 的 hostVisible、portVisible、bulkHostVisible 均假；VPN 信息保持基线。response=204、actualHttpProxyUsed=true，ordinaryProperty 非空。
6. V06：仅 VPN 开启：proxyFixture metadata 仍可见，真实 HTTP 代理请求仍成功。验证 VPN 和代理开关独立。
7. V07：五项全开，HTTPS internet=204，实际代理仍成功。
8. V08：停止夹具 VPN，重新读 A 全关状态：VPN API 为未开启，普通联网正常；再次启动真实 VPN 后检查保护结果仍一致。

## X · 截图所有已有读取与信号

先创建专用 `Pictures/ShieldProbe/` 测试目录，放入有效 PNG 的 `ordinary_probe.png` 和 `Screenshot_probe.png`。后者是按文件名构造的测试图片，不能替代真实 SystemUI 截图。通过 MediaStore scan_file 完成索引，真实系统选图授权另行取得。

X01：模块禁用/作用域外的基线必须能读取截图图片和普通图片，不能因无权限而“屏蔽”。后续开启截图方法和关闭截图方法各执行一遍 X02–X09：

1. X02：检查 Java File.exists、FileInputStream、NIO exists、普通目录枚举。截图根据开关隐藏/可见，普通文件始终可见。
2. X03：native open/openat/fopen/stat/access/readdir、syscall open/stat/getdents 都分别检查截图和普通文件。
3. X04：用独立系统打开得到的已有 FD 检查 read/pread/readv/preadv/fstat/mmap、dup/fcntl、syscall read/statx、libc statx、procfd readlink/open/realpath、procroot、symlink。所有截图读取随开关变化，普通 FD 正常。
4. X05：非截图 syscall getpid、六参数 mmap 非零 offset，以及支持平台的 clone 新栈控制通过，无挂起/崩溃。
5. X06：MediaStore legacy、Bundle、client、id-only 投影查询，截图启用时仅保留普通行，关闭时返回两行；投影列数不变。
6. X07：从 shell 写新增 screenshot 和 ordinary 文件，插入对应媒体行并 drain。Java FileObserver/native inotify 收到 ordinary 事件；截图开启时 screenshot 事件为 0，关闭时大于 0。另复制有效 PNG 并通过 scan_file 建立真实 MediaStore 行，再实际执行 update（修改 display_name，保留原有截图或普通命名）、delete；普通图片的新增、改名、删除每次均触发 ContentObserver，截图图片仅在关闭屏蔽时触发。系统发集合通知时也按此判断。按关闭→开启→再次关闭执行，命令均经过真实 MediaStore；不要构造假的 FileObserver 或 ContentObserver 回调。`_size` 是系统维护的字段，直接改它可能被忽略；只有索引而没有真实文件的行，其删除也可能不发通知。这两种情况均不能作为实际图片变化基线。
7. X08：发送动态和 manifest 截图测试广播、普通广播。截图广播随开关拦截，普通广播始终收到。广播命令返回后，等待实际 onReceive 并刷新检查结果；先确认普通广播已收到，再判断截图广播。执行器最多等待 5 秒，不使用发送后第一份快照作判定。使用命名的测试 action，不把测试广播当系统实际发出。
8. X09：从真实系统选图器分别选择两种图片。document count、列数、打开结果正确；普通图片始终可用。保留授权，不能直接传未授权 URI。

X10：SystemUI 真截图。A 前台，截图关闭时发 `input -d 0 keyevent SYSRQ`，要求官方 callback 和原始 Binder callback 都收到，未注入 shell 的 MediaStore 有新增真实截图。开启截图并冷启动后再拍：系统仍保存图片，两种 callback 都为 0。再关截图重拍恢复收到。`adb screencap` 只用于 PNG 夹具，不计官方回调证据。

X11：通知、剪贴板、无障碍构造内容。低层 Probe 构造截图/普通对象，并验证 screenshot 信号随开关隐藏、普通信号保留；包名含 screenshot 的普通无障碍对象不应误拦截。此项与 X12 服务真实传递分开记录。

X12：打开验证器原有截图日志主页，启用通知读取与无障碍服务、保持前台剪贴板访问。先为临时 C 授予 POST_NOTIFICATIONS，确认 UID 与包级 POST_NOTIFICATION AppOps 均允许；包级 allow 不能覆盖 UID 层 ignore。从未注入的 C 分别发布命名的 screenshot/ordinary 测试通知，再由 A 的真实通知服务读取；先确认 ordinary 已实际收到。验证每条服务连接状态，发布测试剪贴板，无障碍通过系统实际事件传递。截图开启时截图内容不可见，普通内容可见。SystemUI 若不发布截图通知，单独记录，不能用命名通知代替 SystemUI 通知证据。未获授权应显示待授权，不能显示保护成功。结束恢复 clipboard、服务和通知，仅取消本次通知。

X13：日志页按源筛选、全部源、重启监听、清空日志、授权后返回、进后台/回前台、选图后返回、旋转；保持监听生命周期正确，无重复 callback、旧 worker、关闭 FD 后再读、离开后仍计数问题。返回日志页时确认 source-filter 实际在前台，并等待本轮全部所需来源重新“就绪”；旧进程日志中的历史就绪记录不能作为新一轮注册完成的证据。

## I · 配置权限、异常及升级

1. I01：A 读取自己的策略成功；A 请求模块包或 B 的策略得到 SecurityException。B/C 读取各自值正确。
2. I02：A 调用 write、insert、update、delete、query 得到拒绝；设置值不变。仅模块设置页能保存。
3. I03：在专用模拟器先备份模块私有配置。把 apps JSON 损坏作为明确异常夹具；重启设置和目标，均不崩溃，使用默认全开。恢复备份。
4. I04：配置含未知关闭 ID；已知方法正常，普通新增方法默认开启。通过页面更改一个已知开关后，未知关闭 ID 仍被保留；避免升级损失将来恢复的设置。
5. I05：强行停止配置 provider 所属包，冷启动目标；记录配置读取是否仍可启动 provider。再明确禁用 PolicyProvider 组件作为不可用夹具，要有 policyLoaded=false 证据，并验证既定全开 fallback。结束重新启用组件。
6. I06：同签名覆盖安装新 APK，定制和权限保持；重启目标使用新代码。模块 native 三库按已启用方法加载，全关时不加载；仅 developer 开启时 developerstate 不加载，debug 开启时加载。
7. I07：SELinux 仍为真实系统状态，设置中始终标待开发。未来实现时在本手册新增真实 enforcing/permissive 基线和读取路径；不改默认策略存储方式。

## K · 加固应用启动兼容

使用已获授权的设备与目标应用；专用模拟器不能代替该 ROM 和该应用版本的真机检查。记录模块 APK 的 SHA-256、系统版本、ABI 和应用版本。

1. K01：目标应用加入整合模块作用域，恢复默认全开并冷启动。至少重复三次，每次确认真正进入首页，不能只看进程存在、原生加载成功或启动页。检查有无 ANR、崩溃，以及原有 VPN/代理提示；不要进行登录或金融业务。
2. K02：通过真实设置页将截图关闭，保存并冷启动；再将截图开启，保存并冷启动。核对 `Policy loaded=true` 和实际启用方法，其他四项保持开启。结束时恢复测试前的定制条目和作用域。
3. K03：如日志有 `existing native redirect retained`，记录符号名和最终安装数量。ARM64 的已有外部 `B` 或 16 字节 `LDR/BR` 跳转应保持原状；普通未改入口的截图、普通文件、已有 FD 和 syscall 检查仍按 X01–X08 执行。被保留入口的原生截图读取可能仍可见，要明确写入报告，不能把首页正常、Java 检查通过或原生库加载成功当成所有原生读取已屏蔽。

## R · 清理与判定

1. R01：停止 C 的 VPN 夹具，确认 tun 消失、互联网仍通。恢复开发者、USB/无线、飞行模式、屏幕旋转、隐藏 API 策略和授权。通知监听通过系统授权命令恢复，不能只写 `enabled_notification_listeners`；NotificationManagerService 的授权缓存可能在应用安装/卸载后把测试授权写回来。卸载 B/C 后再次核对服务设置与备份完全一致。
2. R02：恢复每个模块原来的启用状态和完整作用域，逐个核对其他应用未被增删。如果专用 userdebug 模拟器需要恢复更低版本的模块，用 `adb -s emulator-5584 install --no-incremental -r -d "<测试前模块APK>"` 保留数据覆盖安装；随后核对安装文件 SHA-256、定制配置和作用域。真机保留经验证的最终版本。
3. R03：删除本轮新增的 MediaStore ID、测试 PNG、临时 uiautomator XML、测试通知；不删除测试前已有图片。卸载 B/C 测试 flavor，保留正式模块和验证器。
4. R04：记录构建、系统/框架版本、每个编号的结果、失败修复、未验证项目。报告保存在 `verification/`；不得写入账号、Cookie、通知正文、剪贴板正文或截图中的个人信息。
5. R05：正常关闭专用模拟器，确认其他模拟器和 vivo 未受影响。

自动执行入口为 `scripts/integration-test.py`。它的用例编号必须与本手册一致，并保存每个场景的实际数据；自动汇总不能替代上述人工操作说明。结果中任何失败或未执行都要说明原因。仅所有适用项通过，且明确列出平台限制，才能把本版本作为该环境中的稳定版本。

各阶段顺序执行，避免两段测试同时点击模拟器界面：

```sh
python3 scripts/integration-test.py prepare
python3 scripts/integration-test.py packaging
python3 scripts/integration-test.py ui
python3 scripts/integration-test.py navigation
python3 scripts/integration-test.py entries
python3 scripts/integration-test.py localization
python3 scripts/integration-test.py matrix
python3 scripts/integration-test.py deep
python3 scripts/integration-test.py media
python3 scripts/integration-test.py scope
python3 scripts/integration-test.py exceptional
python3 scripts/integration-test.py networks
python3 scripts/integration-test.py detector
python3 scripts/integration-test.py reboot
python3 scripts/integration-test.py cleanup
python3 scripts/integration-test.py shutdown
python3 scripts/test-report.py
```

修复测试后，可对有完整前置状态的独立场景使用 `--case` 重跑，例如 `python3 scripts/integration-test.py navigation --case U20-reinstalled-default`；其他已通过场景保留结果。依赖前置步骤的场景仍须先满足相应配置和权限。

第一次 prepare 前完成 P03 备份，准备记录不能被重跑覆盖。prepare 只接受没有现存 VPN 的环境；如果上一轮 C 夹具仍运行，先停止自己的夹具，不替换用户 VPN。MediaStore 命令以 Android shell UID 执行，不能把 root 命令报错但退出码为零当作删除成功。异常阶段允许损坏配置夹具，其他阶段一律通过设置页保存。

`verification/INTEGRATION-REPORT.md` 和 `manual-coverage.json` 按每个手册编号汇总；`integration-results.json` 保存实际读取，previousRuns 保留修复前的失败。entries 阶段操作 P05 的真实 Vector/桌面入口和 D01 的系统开关。布局 PNG 还需要人工检查，单看按钮坐标不足以判断长文字和大字体可用。最近任务要按 AppStateShield 名称选择，边缘露出的卡片可能属于别的应用。
