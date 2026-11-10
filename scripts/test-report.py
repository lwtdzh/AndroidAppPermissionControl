#!/usr/bin/env python3
"""Render the current device evidence against every persisted manual step."""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "verification"
report = json.loads((OUT / "integration-results.json").read_text())
cases = report["cases"]
coverage = {}


def covers(ids, keys, note):
    for ident in ids.split():
        coverage[ident] = (keys.split(), note)


covers("P01 P02 P04", "P01-P02/P04", "四 ABI APK、签名、已安装版本及专用 AVD。")
covers("P03", "P03-P07/V01/D01 P03-capture-script", "原始备份保持；实际只读采集、600 权限和拒绝覆盖另经验证。")
covers("P06", "P03-P07/V01/D01", "独立模块作用域；旧模块对三个目标不重复注入。")
covers("P07", "P03-P07/V01/D01 P07-clipboard-backup", "真实授权；未注入的 C 在矩阵测试前保存剪贴板。")
covers("P05", "P05", "实际桌面应用列表与 Vector 模块设置入口。")
covers("U01", "U01", "空定制列表、默认全开和 SELinux 待开发说明。")
covers("U02 U03 U04", "U02-U04", "按名称/包名搜索、大小写、无匹配、清空和系统筛选。")
covers("U05 U06 U07 U08 U09", "U05-U09/U23", "取消、继续编辑、丢弃、保存全开和重复选择。")
covers("U10 U11 U12 U13", "U10-U13", "替换旧配置、全部开启和关闭已实现方法。")
covers("U14 U15", "U14-U16", "编辑草稿和选择器在横竖屏重建后保持。")
covers("U16", "U14-U16 U16-recents", "后台进程结束、实际最近任务返回与强行停止后的差别。")
covers("U17 U18 U19", "U17-U20", "取消/确认恢复默认、多个应用独立保存、卸载条目删除。")
covers("U20", "U17-U20 U20-reinstalled-default", "删除已卸载条目；重装后重新关联 Vector 作用域，实际读取使用全开默认。")
covers("U21", "U21 U21-top-layout U21-gesture", "大字体横竖屏上下部、长包名、实际手势返回；截图人工检查。")
covers("U22", "U22 U22-labels", "六种语言的标题、五项开关与保存/取消文字；配置保持。")
covers("U23", "U05-U09/U23 U23-repeat", "重复选取和连续保存/返回，无重复条目。")
covers("S01", "S01", "模块禁用但有作用域，读取真实系统状态。")
covers("S02", "S02/S07-S08", "模块启用但目标不在作用域，无注入。")
covers("S03 S04 S05", "S03 S04 S05", "无定制、全开定制和全部关闭分别核对实际读取。")
covers("S06 S09", "S06/S09", "运行中策略不变、冷启动采用新策略；三个早期生命周期。")
covers("S07 S08", "S07-S08", "作用域外创建定制、加入作用域生效、移出恢复且定制保留。")
covers("S10 S11", "S10-S11 M33/S10", "不同 UID 独立配置、:vpn 独立进程及模拟器重启。")
for number in range(32):
    bits = format(number, "05b")
    covers("M" + bits, "M" + bits, "真实界面保存后冷启动；状态、低层截图读取及普通操作。")
covers("M33", "M33/S10", "A=10101，B=01010，C 默认全开。")
covers("M34", "M34", "只改变 A，B/C 保持原有结果。")
covers("M35", "M35", "删除 A 定制恢复全开，B 定制保持。")
covers("D01", "D01-system-ui", "实际开发者选项页面与 USB 调试开关、shell 真实开启值。")
covers("D02 D03 D04 D05 D06 D07", "M00000 M00010 M00001 M00011",
       "32 组合中的 Global/Secure/System、call/query、Java/native 属性和普通控制。")
covers("D08", "D08", "无线调试真实开启基线；平台恢复为零时单独标为未验证。")
covers("V01", "P03-P07/V01/D01", "实际 VpnService 同意与 TUN 建立。")
covers("V02 V03 V05 V06 V07", "M00000 M01000 M00100 M11111",
       "真实 VPN 观察、独立代理 metadata、真实代理 HTTP 及 HTTPS 204。")
covers("V04", "V02-V07/V04-ten-cold-starts/D02-D07", "真实网络回调和十次冷启动 native 列表成对释放。")
covers("V08", "V08", "停止 VPN、无 VPN 基线、重新开启及再次保护。")
covers("X01", "S01 S02/S07-S08", "无注入基线同时读取截图与普通图片，排除权限造成的假成功。")
covers("X02 X03 X04 X05 X06 X07 X08 X09 X10 X11",
       "X02-X11-disabled X02-X11-enabled X02-X11-disabled-restored",
       "关闭→开启→恢复：已有 FD、syscall、媒体、真实事件、真实选图授权及 SystemUI 截图。")
covers("X07", "X02-X11-disabled X02-X11-enabled X02-X11-disabled-restored X07-media-disabled X07-media-enabled X07-media-disabled-restored",
       "普通/截图文件事件；真实 MediaStore insert/update/delete，集合通知的普通变化保留。")
covers("X12", "X12-disabled X12-enabled X12-disabled-restored",
       "真实通知/无障碍服务和前台剪贴板传递；构造内容与系统截图分开记录。")
covers("X13", "X13", "全部 19 种源选择、重启监听、清空、旋转、后台、选图与授权页面返回。")
covers("I01 I02 I06", "I01-I02/I06", "同 UID 自读、跨 UID/写拒绝、按方法加载 native 库和同签名升级。")
covers("I06", "I01-I02/I06 I06-final-upgrade", "按方法加载 native 库；最终签名 APK 覆盖安装保留定制。")
covers("I03", "I03", "损坏配置 JSON：页面与目标不崩溃，默认全开；恢复备份。")
covers("I04", "I04", "页面保存保留未知关闭 ID；其他将来方法默认开启。")
covers("I05", "I05", "强行停止后 provider 自启动；禁用 provider 时 policyLoaded=false 并全开回退。")
covers("I07", "I07 U01", "SELinux 保持真实状态；设置标注待开发，本版没有该方法。")
covers("R01 R02 R03 R04", "R01-R04", "恢复原设置、作用域、权限和服务，只删除本次新增图片/夹具。")
covers("R05", "R05", "仅关闭 emulator-5584，其他设备保持原状。")

labels = {"passed": "通过", "failed": "失败", "platform-limited": "平台限制", "missing": "未执行"}
rows = []
statuses = []
for ident, (keys, note) in coverage.items():
    values = [cases.get(key, {}).get("status", "missing") for key in keys]
    status = next((v for v in ("failed", "missing", "platform-limited") if v in values), "passed")
    statuses.append(status)
    rows.append(f"| {ident} | {labels[status]} | {'、'.join(keys)} | {note} |")
matrix = sum(cases.get("M" + format(n, "05b"), {}).get("status") == "passed" for n in range(32))
complete = not any(s in ("failed", "missing") for s in statuses)
text = [
    "# 应用状态屏蔽 0.2.0 · 模拟器测试记录", "",
    ("所有适用步骤已通过。" if complete else "验证尚未结束，见下表未执行或失败的步骤。")
    + f"五种方法的实际开关组合通过 {matrix}/32。", "",
    "环境：专用 ScreenshotShield_API36，emulator-5584，Android 16 / API 36 / ARM64，Vector。"
    "四 ABI 构建与 ARM64 运行分别记录。", "",
    "SELinux 尚未实现。无线调试开启基线不能保持时，只证明当前零值路径；"
    "不将其写为开启状态屏蔽通过。动卡空间与 vivo 本轮未测试。", "",
    "人工步骤在 `docs/TEST-MANUAL.md`，完整实际数据在 `verification/integration-results.json`。"
    "表中的证据键对应 JSON 的 cases；previousRuns 保留重跑前的结果。", "",
    "| 手册步骤 | 结果 | 实际证据 | 检查内容 |", "|---|---|---|---|", *rows, "",
    "## 交付 APK 的 SHA-256", "",
]
for name, digest in report.get("artifacts", {}).items():
    text.append(f"- {name}：`{digest}`")
text += ["", "## 平台限制及实际修复", ""]
for key, value in cases.items():
    if value.get("status") == "platform-limited":
        text.append(f"- {key}：{value.get('evidence', {})}")
text += [
    "- API33+ 设置页注册系统手势返回，旧版本保留 onBackPressed；未保存修改经过确认。",
    "- 验证器旋转保留日志源；退出页面后旧 worker 不再发布结果。",
    "- 设置测试先清空保留的搜索词，再输入新搜索词；横屏滑动使用旋转后的实际屏幕尺寸。",
    "- 最近任务测试等待 Android 停止页面并保存状态，再按名称选中央卡片；过早杀进程和边缘卡片点击分别记录为测试问题。",
    "- 测试前从未注入的 C 私下备份剪贴板；结束恢复原定制、语言、权限及剪贴板。",
    "- Vector 2.2 在 B 重装且 UID 改变后保留旧作用域条目，但没有注入；取消并重新勾选作用域后恢复。此步骤写入 U20，不把列表勾选当注入证据。",
    "- MediaStore 夹具以 Android shell UID 操作并检查异常输出，避免 root 无包名造成的删除失败。",
    "- 截图的关闭、开启、再次关闭使用固定证据编号；定向重跑会替换对应结果并保留 previousRuns。",
    "- M11001 曾返回 UnknownHostException；未注入对照返回 204，原失败保留。测试启动加 clear-top，避免 C 的旧任务把夹具页带到前台而未运行 Probe。",
    "- 首次重启检查在 Wi-Fi 尚未就绪时启动：原快照没有 wlan0、没有 Wi-Fi transport，HTTPS 返回 UnknownHostException。重启阶段现等待系统侧 wlan0 UP 与当前 Wi-Fi 网络 VALIDATED，再建立 VPN 并测试；原失败保留，不用重开目标掩盖失败。",
    "- 清理曾只写回 enabled_notification_listeners；卸载测试应用后，NotificationManagerService 把缓存的测试授权写回来。现用系统 allow_listener/disallow_listener 恢复原授权，再写回设置并在卸载后核对；原失败和重新执行结果均保留。",
    "- 广播命令返回不代表 onReceive 已运行；测试先等普通事件实际送达再检查截图事件。",
    "- 修复旧截图方法对集合通知一律抑制的问题：注册时保存普通行元数据，只有普通行实际变化才放行不带 ID 的相册通知。真实插入、修改、删除和系统截图分别复测。",
    "- 媒体变化基线使用有效 PNG、scan_file 和真实改名/删除；系统可能忽略 _size 写入，空索引行删除也可能不通知。这些旧测试夹具失败保留在 previousRuns。",
    "- 验证器 VPN 停止命令直接关闭 TUN 并移除前台通知。系统的 VPN 绑定曾使 stopSelf 后的 onDestroy 延迟，原实现没有及时释放接口；实际停启与清理步骤复测。",
    "- 真实通知测试同时授予 POST_NOTIFICATIONS、允许 UID 和包级 AppOps；只允许包级操作时 UID 的 ignore 仍阻止发送。",
    "- 日志页重新回前台后等待当前一轮来源注册完成；媒体与文件 observer 在实际注册后才报告就绪。Java 文件 observer 同时监听 CREATE；旧页面停止时只清除自己的 Signals.listener。",
    "- 修复页面重建交叠：新页开始监听前停止上一页。原先旧页延迟清理删除了共享 Java inotify 的新 watch，首次截图可见、返回后 Java 文件来源丢失；真实返回流程与 13 个来源重新验证。",
    "- 权限/API 范围通过 lint 检查；官方截图回调仅在 API34+ 运行。", "",
]
(OUT / "INTEGRATION-REPORT.md").write_text("\n".join(text) + "\n")
(OUT / "manual-coverage.json").write_text(json.dumps({
    ident: {"status": statuses[index], "evidenceKeys": keys, "checks": note}
    for index, (ident, (keys, note)) in enumerate(coverage.items())
}, ensure_ascii=False, indent=2) + "\n")
print(f"Rendered {len(coverage)} manual rows; matrix {matrix}/32; complete={complete}")
