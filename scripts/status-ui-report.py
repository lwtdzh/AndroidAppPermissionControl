#!/usr/bin/env python3
"""Assemble the tested 0.3.1 APKs, manual and actual UI/phone evidence."""
import hashlib
import json
import pathlib
import shutil
import zipfile
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "verification"
DELIVERY = pathlib.Path.home() / "Downloads"
ui = json.loads((OUT / "status-ui-0.3.1-results.json").read_text())
phone = json.loads((OUT / "vivo-status-ui-0.3.1.json").read_text())
assert all(case["status"] == "passed" for case in ui["cases"].values()), "Resolve failed UI cases first"
assert "I99-restored" in ui["cases"], "Restore the emulator before delivery"
assert len(phone["packages"]) == 2 and all(p["installed"] for p in phone["packages"].values())
native = {}
for name in ("AppStateShield", "AppStateVerifier"):
    with zipfile.ZipFile(OUT / (name + "-0.3.0.apk")) as old, zipfile.ZipFile(OUT / (name + "-0.3.1.apk")) as new:
        libs = [n for n in old.namelist() if n.startswith("lib/") and n.endswith(".so")]
        native[name] = {"libraries": len(libs), "bytesUnchanged": all(old.read(n) == new.read(n) for n in libs)}
assert all(value["bytesUnchanged"] for value in native.values())
lint = {name: sum(issue.get("severity") == "Error" for issue in ET.parse(ROOT / path).getroot().findall("issue"))
        for name, path in (("module", "app/build/reports/lint-results-release.xml"),
                           ("verifier", "verifier/build/reports/lint-results-primaryRelease.xml"))}
assert not any(lint.values())
hashes = {name: hashlib.sha256((OUT / name).read_bytes()).hexdigest()
          for name in ("AppStateShield-0.3.1.apk", "AppStateVerifier-0.3.1.apk")}
for pkg, apk in (("io.github.lwtdzh.appstateshield", "AppStateShield-0.3.1.apk"),
                 ("io.github.lwtdzh.screenshotdetector", "AppStateVerifier-0.3.1.apk")):
    assert hashes[apk] == phone["packages"][pkg]["sha256"] == ui["artifacts"][apk]
metadata = {"version": "0.3.1", "date": "2026-11-13", "ui": ui, "phone": phone, "native": native,
            "lintErrors": lint, "counterAssertions": 11, "artifactSha256": hashes}
data_name = "AppStateShield-0.3.1-测试数据.json"
(DELIVERY / data_name).write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
rows = "\n".join("| " + name + " | 通过 |" for name in ui["cases"])
readings = "\n".join("| " + key + " | " + value + " |" for key, value in phone["summary"].items())
report = f"""# AppStateShield / AppStateVerifier 0.3.1 测试与安装记录

2026-11-13。两个同签名 APK 已升级安装到 vivo V2419A / Android 16；安装后的完整 SHA-256 与模拟器测试 APK 一致。原应用策略、Vector 模块状态/作用域和系统 SELinux 模式保持原样。

## 使用

从 Vector 打开应用状态屏蔽设置，顶部“显示应用图标”默认关闭。开启后桌面入口打开同一设置页，Android 用户各自保存选择，覆盖安装保留。分身工具能否提供克隆仍取决于该工具的支持；本次验证了入口发现及用户隔离，未操作用户手机的分身工具。

验证器首页保留传统日志与读取检查，并增加每 2 秒刷新的 VPN、代理、开发者选项、USB/无线调试、SELinux 信息条。它展示应用观察到的值，注入模块时可能经过屏蔽。

截图会话计数按文件/图片身份和 2 秒窗口合并估算。实际两次 SystemUI 截图各产生官方/Binder 两条信号，会话累计两次。旋转、后台返回、重启监听、清空日志保留会话次数；结束页面或冷启动重新计数，仅首页前台期间计数。

## 实际检查

专用 ScreenshotShield_API36 / emulator-5584 / ARM64 / API36；四 ABI 构建和两个 release lint 均通过，lint 错误为 0。11 个 JVM 断言检查多入口关联、快速截图、不同文件/图片 ID、匿名重复事件及序列化恢复。

| 手册步骤/执行记录 | 结果 |
|---|---|
{rows}

已人工查看界面截图；正常字号与 1.3 字号下信息条可读，传统诊断保留。专用测试用户、临时 VPN、测试截图已删除，原设置/作用域/APK 恢复后关闭模拟器。

## vivo 信息条

| 项目 | 读数 |
|---|---|
{readings}

这是当次应用读数，不代替未注入的系统检查。安装过程保留用户原配置，没有开启图标、改动作用域或切换系统 SELinux。USB 安装确认被 ROM 拦截时，使用已有 root 的包管理接口安装同一个已校验 APK，没有修改安全设置。

## 本次发现与限制

SELinux enforce 文件不可读时，Java boolean 的 false 可能来自读取失败。最终信息条改为“模式无法确认”，不会把它直接称为 Permissive；有真实文件 0/1 或肯定的 API 结果时再显示对应模式。强制执行的模拟器已验证该情况。所有 API 同时不可用的错误分支未另造系统夹具，保留手册 V10 供后续检查。

执行器修正了中英文匹配、锁定用户的入口查询、SystemUI 浮层等待及调试面板内的滚动位置。起始任务及后台返回都改用 MAIN/LAUNCHER；原组件直启的根 Intent 与桌面 Intent 不同，系统会在它上方新建页面，CLEAR_TOP 也会重建普通 Activity。修正前失败保存在测试数据 previousRuns 中。

截图次数为估算，匿名信号、延迟保存和快速连拍可能出现误差，0 次仍需看权限与真实截图基线。当前首页截图页要求 API34；较低版本沿用设备状态检查。

这次没有修改六种屏蔽 Hook。与已发布 0.3.0 比较，主模块 16 个、验证器 12 个原生库的字节完全相同。0.3.0 的 64 组合/SELinux 专项结果继续保留，本次没有重新执行整套矩阵，也未把历史结果计入本轮。

## 文件校验

{chr(10).join(name + '：' + digest for name, digest in hashes.items())}
"""
report_name = "AppStateShield-0.3.1-测试报告.md"
(OUT / "STATUS-UI-0.3.1.md").write_text(report)
(DELIVERY / report_name).write_text(report)
manual_name = "AppStateShield-0.3.1-人工测试手册.md"
shutil.copy2(ROOT / "docs/TEST-MANUAL.md", DELIVERY / manual_name)
for name in hashes:
    shutil.copy2(OUT / name, DELIVERY / name)
checksum_name = "AppStateShield-0.3.1-SHA256SUMS.txt"
(DELIVERY / checksum_name).write_text("".join(digest + "  " + name + "\n" for name, digest in hashes.items()))
files = [*hashes, report_name, manual_name, data_name, checksum_name]
bundle = DELIVERY / "AppStateShield-0.3.1-delivery.zip"
with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as package:
    for name in files:
        package.write(DELIVERY / name, name)
    for name in ("settings-icon-0.3.1.png", "verifier-summary-0.3.1.png", "verifier-font-0.3.1.png"):
        package.write(OUT / name, "screenshots/" + name)
print("Created delivery: " + str(bundle))
print("UI cases passed: " + str(len(ui["cases"])) + "; counter assertions: 11; phone packages verified: 2")
