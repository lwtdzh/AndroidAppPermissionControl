#!/usr/bin/env python3
"""Render the SELinux evidence without treating old release reports as new tests."""
import json
import pathlib

root = pathlib.Path(__file__).resolve().parents[1]
report = json.loads((root / "verification/selinux-0.3.0-results.json").read_text())
cases = report["cases"]
matrix_keys = [f"M6-{n:06b}" for n in range(64)]
required = matrix_keys + [
    "L00-capture", "L01-prepare", "L02-unscoped-permissive", "L03-all-off", "L04-selinux-only", "L05-all-on",
    "L06-enforcing-baseline", "L06-enforcing-all-off", "L07-enforcing-selinux-only",
    "L08-independent-A", "L09-independent-B", "L10-default-future-method", "L11-https-policy-isolation",
    "L12-ten-cold-starts", "L13-native-selinux-only", "L13-native-screenshot-only", "L13-native-all-on", "L99-restored",
]
matrix = sum(cases.get(k, {}).get("status") == "passed" for k in matrix_keys)
failed = [k for k in required if cases.get(k, {}).get("status") != "passed"]
text = [
    "# AppStateShield 0.3.0 · SELinux 验证记录", "",
    f"当前已通过 {sum(v['status'] == 'passed' for v in cases.values())} 项，64 个组合已通过 {matrix}/64。",
    "尚未通过：" + ("、".join(failed) if failed else "无") + "。", "",
    "环境为 ScreenshotShield_API36 / emulator-5584、Android 16 API36、ARM64、Vector。"
    "四 ABI 已编译；其他 ABI、ROM 与真机的 0.3.0 运行未验证。", "",
    "开启 SELinux 方法后，应用的 Java SELinux API、libselinux 导出状态函数及支持的 enforce 文件读取"
    "返回 Enforcing / 1。每份 Permissive 样本同时核对未注入 shell 的真实模式，"
    "系统仍为 Permissive。关闭方法后恢复 false / 0。Enforcing 条件也单独检查："
    "该 ROM 下未注入应用无法读取 enforce，文件错误保持原样；"
    "Java 与 libselinux 状态 API 开启后仍返回 true / 1。", "",
    "## 真实模式对照", "",
    "| 系统模式 / 用例 | Java enforced | libselinux getenforce | FileInputStream | native read |",
    "|---|---|---|---|---|",
]
for key in ("L02-unscoped-permissive", "L03-all-off", "L04-selinux-only", "L05-all-on",
            "L06-enforcing-baseline", "L06-enforcing-all-off", "L07-enforcing-selinux-only"):
    value = cases.get(key, {}).get("evidence")
    if value:
        text.append(f"| {key} | {value['javaEnforced']} | {value['native']['security_getenforce']} |"
                    f" {value['fileInputStream']} | {value['native']['read']} |")
text += ["",
    "64 组合通过真实设置页保存后冷启动。每行检查 SELinux、三个早期生命周期、"
    "开发者与 USB 调试、Java/native VPN 接口、代理信息及真实代理 HTTP 204、构造截图文件与普通文件、"
    "按需加载的 native 库。构造截图文件不代表真实 SystemUI 截图事件；"
    "原 0.2.0 的真实截图/授权结果与 0.2.1 的 vivo 兼容结果保留，未冒充本轮证据。", "",
    "## 读取与普通操作", "",
    "| 检查 | 本轮记录 |", "|---|---|",
    "| Java | isSELinuxEnabled / isSELinuxEnforced、FileInputStream、RandomAccessFile、Files.readAllBytes、FileChannel |",
    "| Native | 真实 security_getenforce / is_selinux_enabled；read、pread、pread64、readv、dup、fread、fgets |",
    "| 文件语义 | EOF、无效 FD 的 EBADF、fread 不完整末项、普通同名文件保持 0 |",
    "| 系统上下文 | getcon/freecon 成对调用成功；模块没有上下文或模式写入逻辑 |",
    "| 普通操作 | 每行本地 HTTP 代理请求成功；L11 检查 HTTPS 204 与配置读写隔离；L12 十次冷启动 |", "",
    "L13 另检查只开 SELinux、只开截图与全开三种配置：普通 PNG 始终可读，"
    "构造截图 PNG 仅随截图开关变化；已有 FD、read/pread/readv/preadv、mmap、procfd、"
    "符号链接和 libc syscall 路径分别核对。getpid、六参数 syscall、clone 新栈保留正常结果。"
    "此项使用构造文件，未执行真实 SystemUI 截图事件。", "",
    "## 实际限制", "",
    "- 直接 syscall / 内联汇编和未注入的 shell 子进程仍可读真实模式。directSyscall 每行明确记录为真实 0。",
    "- 仅识别 /sys/fs/selinux/enforce 与 /selinux/enforce；其他挂载路径、未 Hook 的读取函数不承诺保护。",
    "- 原始读取失败时保留失败，不伪造文件成功；Enforcing 下的文件权限错误不算返回 1 的证明。文件保护证据来自真实可读的 Permissive 基线。",
    "- ARM64 加固库已有外部跳转会保留，相关 native 入口可能未屏蔽；没有用正常启动代替读取证据。",
    "- 模拟器没有 ro.boot.selinux 值；确认缺失属性及调用方默认值不变。非空启动属性改写尚无真实基线。",
    "- 无线调试开启状态仍没有可保持的基线；不把当前零值当成开启状态屏蔽通过。", "",
    "## 开发中修复与验证", "",
    "初次测试发现 Vector 不允许同一 libc 入口重复 Hook。改为在本模块已经安装的截图读取函数、"
    "开发者属性函数中注册 SELinux 过滤器，组合场景继续使用一次原生 Hook。"
    "另补齐 native_init 的库注册，修正缺失系统属性带默认值时的读取；"
    "验证器从真实已加载 ELF 调用 libselinux，避免 Android 私有库 namespace 限制导致没有基线。", "",
    "## 各场景", "", "| 用例 | 状态 |", "|---|---|",
]
text += [f"| {key} | {'通过' if value['status'] == 'passed' else '失败'} |"
         for key, value in sorted(cases.items())]
text += ["", "## 构建与文件", ""]
text += [f"- {name}：{digest}" for name, digest in report["artifacts"].items()]
text += ["", "完整读数见同目录 selinux-0.3.0-results.json；步骤见 docs/TEST-MANUAL.md 的 L 节。",
         "交付包也附有 AppStateShield-0.3.0-人工测试手册.md，包含相同步骤。",
         "恢复结果见 L99；原始本机快照保持仓库外、600 权限。", ""]
(root / "verification/SELINUX-0.3.0.md").write_text("\n".join(text))
print(f"Rendered SELinux report: {matrix}/64 combinations; failed={failed}")
