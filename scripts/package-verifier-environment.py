#!/usr/bin/env python3
"""Deliver final APKs and current verifier evidence; report phone installation accurately."""
import hashlib
import json
import pathlib
import shutil
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
VER = ROOT / "verification"
STATE = pathlib.Path.home() / "Library/Application Support/ScreenshotShield/verifier-environment-0.4.12"
DEST = pathlib.Path.home() / "Downloads/AppStateShield-0.4.12-environment"
RESULT = json.loads((VER / "verifier-environment-0.4.12-results.json").read_text())
ARTIFACTS = json.loads((VER / "verifier-environment-0.4.12-artifacts.json").read_text())
RESTORED = json.loads((VER / "verifier-environment-0.4.12-restoration.json").read_text())
UNIT = json.loads((VER / "verifier-environment-0.4.12-unit.json").read_text())
assert len(RESULT["cases"]) == 8 and all(row["status"] == "passed" for row in RESULT["cases"].values())
assert RESTORED["passed"] and RESTORED["exactFileTreeAndSHA256"] and UNIT["passed"]
PHONE = VER / "vivo-environment-0.4.12-installed.json"
phone = json.loads(PHONE.read_text()) if PHONE.exists() else None


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


for name, product in (("AppStateShield", "AppStateShield"), ("AppStateVerifier", "AppStateVerifier")):
    filename = name + "-0.4.12.apk"
    assert sha(VER / filename) == ARTIFACTS[product]["sha256"] == RESULT["artifacts"][filename]
    if phone:
        pkg = "io.github.lwtdzh.appstateshield" if name == "AppStateShield" else "io.github.lwtdzh.screenshotdetector"
        assert phone["packages"][pkg]["installed"] and phone["packages"][pkg]["sha256"] == sha(VER / filename)

rows = "\n".join("| " + key + " | 通过 | " + str(value["seconds"]) + " |" for key, value in RESULT["cases"].items())
status = ("两个 0.4.12 APK 已覆盖安装到 vivo V2419A；文件哈希、版本、UID、配置哈希、权限、Vector 作用域/启用状态和系统 SELinux 状态均已核对，检测器环境结果已显示。"
          if phone else "尚未安装到手机：本轮最终检查时 ADB 未识别到已授权的 vivo V2419A。APK 和安装脚本已准备好，连接手机后继续覆盖安装。")
text = f"""# AppStateShield / 应用状态验证器 0.4.12

验证器每次进入首页自动检查系统环境，并把逐项结果打印到首页日志与 EnvironmentProbe Logcat。首页可展开详情、手动刷新；结果使用 AtomicFile 保存到私有 files/environment-result.json。环境日志不增加截图次数。新旧状态页共用 EnvironmentOverview。

检查包括 Java/libc/直接 syscall 的 Su/Busybox/Root 文件，maps/加载器中已知框架库，可见 Xposed 模块与类，构建及 DLKM 属性，VPN、代理、开发者/调试和 SELinux，以及 AndroidKeyStore 新生成的证明。证明逐项检查链签名、有效期、Google 根公钥匹配、随机 challenge、安全级别与启动字段，完成后只删除本次临时密钥。不联网、不执行 su、不修改系统模式、不申请设备 ID 证明。

## 本轮实测

JDK17 解析测试 {UNIT['assertions']} 项通过；两个 APK 构建及 lint 通过；四 ABI 均编译。正式 APK 不包含调试厂商/原生夹具。签名身份与 0.4.11 相同，模块及检测器原有 native 库的字节完全一致。模块只更新版本号。

专用 ScreenshotShield_API36 / emulator-5584，API36 ARM64，原 Magisk/Vector 环境，系统模式 {RESULT['environment']['rootMode']}。下表为最终 APK 的实际检查，详细读数和修复过程见 evidence/。API28–33 路由已编译并在 API36 上执行旧状态页面；未在真实 API28–33 系统运行。

| 用例 | 结果 | 最终通过用时（秒） |
|---|---|---|
{rows}

未注入基线读到原测试根、Software 证明/KeyMint、deviceLocked=false、Unverified 和全零启动字段。开启六项屏蔽后 USB 调试读数改变；机型/隐藏模块列表开启后 Java/native 构建及 DLKM tags 变为 release-keys，可见模块数为 0，而签名证明字段保持原值。手动刷新和后台返回保持主 PID，临时密钥清理完成。

本轮修复一个实测发现的解析错误：RootOfTrust 的 ASN.1 标签应为 704；709 是 attestationApplicationId。补充两种不同标签的对照后，模拟器实际证明能完整展开。未把 APK 内的数据当成预先正确的结果。

本轮的路径扫描并未排除所有注入：模块标记 injected=true 时，原 Magisk/Vector 环境的 maps 仍没有已知框架库名，shell 真实 maps 也如此。存在 memfd/jit-cache 映射，但不能直接指认它们属于某个框架库。0.4.11 的 SukiSU/ZygiskNext 则确实给出具名路径。两份环境记录各自保留来源。

## 尚不能修复的原因

完整说明见 docs/DETECTOR-LIMITATIONS-0.4.11.md。README 和 AGENTS 已加入后续 Agent 必须保留的具体原因：

- Vector/Zygisk 的真实原生注入痕迹尚无保持模块正常运行的已验证隐藏方法，Native Detector 的具体枚举算法尚未确认。
- 原模拟器使用测试证明根；模块没有受信任 CA 的签发能力。
- 证明安全级别与 KeyMint 都是 Software；进程 Hook 不能建立 TEE/StrongBox 硬件隔离。
- deviceLocked、verifiedBootState、verifiedBootKey、verifiedBootHash 来自实际启动环境与密钥服务；修改应用参数不能建立 AVB 链，也不能改写证书而保留原签名。
- 该模拟器缺少设备 ID 证明功能，属于无法验证，不计作新增失败。

权限拒绝显示“无法确认”；未知 Google 根可能是厂商根；非零哈希也不能单独证明生产启动链。检查不含在线吊销或远端完整性验证，也不声称等同于三款外部检测器的所有算法。

0.4.11 的第三方 81 次检测与六项组合报告仍保留原 APK/平台归属；本轮没有修改 Hook 或策略，因此没有重新跑 64 组合，也没有将旧运行结果改记为 0.4.12。

## 环境恢复与手机安装

专用模拟器已停止，完整原 AVD 已恢复，文件树、权限和每个文件的 SHA-256 均匹配原快照；未操作其他模拟器。

{status}

## 文件

- AppStateShield-0.4.12.apk：模块，版本代码 22。
- AppStateVerifier-0.4.12.apk：保留原包名的检测器，版本代码 18。
- evidence/：本轮 JSON、日志、截图、解析与最终 APK 审计、环境恢复记录。
- docs/：检测能力及不可修复原因。
- SHA256SUMS.txt：交付文件校验值。
"""
(VER / "VERIFIER-ENVIRONMENT-0.4.12-REPORT.md").write_text(text)
DEST.mkdir(parents=True, exist_ok=True)
(DEST / "evidence").mkdir(exist_ok=True)
(DEST / "docs").mkdir(exist_ok=True)
for filename in ("AppStateShield-0.4.12.apk", "AppStateVerifier-0.4.12.apk"):
    shutil.copy2(VER / filename, DEST / filename)
    shutil.copy2(VER / filename, DEST.parent / filename)
shutil.copy2(VER / "VERIFIER-ENVIRONMENT-0.4.12-REPORT.md", DEST / "REPORT.md")
for filename in ("VERIFIER-ENVIRONMENT.md", "DETECTOR-LIMITATIONS-0.4.11.md"):
    shutil.copy2(ROOT / "docs" / filename, DEST / "docs" / filename)
for path in VER.glob("verifier-environment-0.4.12-*"):
    if path.is_file():
        shutil.copy2(path, DEST / "evidence" / path.name)
shutil.copy2(VER / "build-0.4.12-environment-final.log", DEST / "evidence")
for path in STATE.glob("environment-*.png"):
    shutil.copy2(path, DEST / "evidence" / path.name)
if phone:
    shutil.copy2(PHONE, DEST / "evidence")
paths = sorted(path for path in DEST.rglob("*") if path.is_file() and path.name != "SHA256SUMS.txt")
(DEST / "SHA256SUMS.txt").write_text("\n".join(sha(path) + "  " + str(path.relative_to(DEST)) for path in paths) + "\n")
archive = DEST.parent / (DEST.name + ".zip")
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
    for path in sorted(DEST.rglob("*")):
        if path.is_file():
            output.write(path, pathlib.Path(DEST.name) / path.relative_to(DEST))
with zipfile.ZipFile(archive) as output:
    assert output.testzip() is None
print("PASS delivery ZIP and checksums; phone installed:", bool(phone))
print(archive)
