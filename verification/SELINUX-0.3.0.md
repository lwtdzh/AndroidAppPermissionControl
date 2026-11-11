# AppStateShield 0.3.0 · SELinux 验证记录

当前已通过 82 项，64 个组合已通过 64/64。
尚未通过：无。

环境为 ScreenshotShield_API36 / emulator-5584、Android 16 API36、ARM64、Vector。四 ABI 已编译；其他 ABI、ROM 与真机的 0.3.0 运行未验证。

开启 SELinux 方法后，应用的 Java SELinux API、libselinux 导出状态函数及支持的 enforce 文件读取返回 Enforcing / 1。每份 Permissive 样本同时核对未注入 shell 的真实模式，系统仍为 Permissive。关闭方法后恢复 false / 0。Enforcing 条件也单独检查：该 ROM 下未注入应用无法读取 enforce，文件错误保持原样；Java 与 libselinux 状态 API 开启后仍返回 true / 1。

## 真实模式对照

| 系统模式 / 用例 | Java enforced | libselinux getenforce | FileInputStream | native read |
|---|---|---|---|---|
| L02-unscoped-permissive | False | 0 | 0 | 0 |
| L03-all-off | False | 0 | 0 | 0 |
| L04-selinux-only | True | 1 | 1 | 1 |
| L05-all-on | True | 1 | 1 | 1 |
| L06-enforcing-baseline | False | -1 | ERROR:FileNotFoundException | ERROR:9 |
| L06-enforcing-all-off | False | -1 | ERROR:FileNotFoundException | ERROR:9 |
| L07-enforcing-selinux-only | True | 1 | ERROR:FileNotFoundException | ERROR:9 |

64 组合通过真实设置页保存后冷启动。每行检查 SELinux、三个早期生命周期、开发者与 USB 调试、Java/native VPN 接口、代理信息及真实代理 HTTP 204、构造截图文件与普通文件、按需加载的 native 库。构造截图文件不代表真实 SystemUI 截图事件；原 0.2.0 的真实截图/授权结果与 0.2.1 的 vivo 兼容结果保留，未冒充本轮证据。

## 读取与普通操作

| 检查 | 本轮记录 |
|---|---|
| Java | isSELinuxEnabled / isSELinuxEnforced、FileInputStream、RandomAccessFile、Files.readAllBytes、FileChannel |
| Native | 真实 security_getenforce / is_selinux_enabled；read、pread、pread64、readv、dup、fread、fgets |
| 文件语义 | EOF、无效 FD 的 EBADF、fread 不完整末项、普通同名文件保持 0 |
| 系统上下文 | getcon/freecon 成对调用成功；模块没有上下文或模式写入逻辑 |
| 普通操作 | 每行本地 HTTP 代理请求成功；L11 检查 HTTPS 204 与配置读写隔离；L12 十次冷启动 |

L13 另检查只开 SELinux、只开截图与全开三种配置：普通 PNG 始终可读，构造截图 PNG 仅随截图开关变化；已有 FD、read/pread/readv/preadv、mmap、procfd、符号链接和 libc syscall 路径分别核对。getpid、六参数 syscall、clone 新栈保留正常结果。此项使用构造文件，未执行真实 SystemUI 截图事件。

## 实际限制

- 直接 syscall / 内联汇编和未注入的 shell 子进程仍可读真实模式。directSyscall 每行明确记录为真实 0。
- 仅识别 /sys/fs/selinux/enforce 与 /selinux/enforce；其他挂载路径、未 Hook 的读取函数不承诺保护。
- 原始读取失败时保留失败，不伪造文件成功；Enforcing 下的文件权限错误不算返回 1 的证明。文件保护证据来自真实可读的 Permissive 基线。
- ARM64 加固库已有外部跳转会保留，相关 native 入口可能未屏蔽；没有用正常启动代替读取证据。
- 模拟器没有 ro.boot.selinux 值；确认缺失属性及调用方默认值不变。非空启动属性改写尚无真实基线。
- 无线调试开启状态仍没有可保持的基线；不把当前零值当成开启状态屏蔽通过。

## 开发中修复与验证

初次测试发现 Vector 不允许同一 libc 入口重复 Hook。改为在本模块已经安装的截图读取函数、开发者属性函数中注册 SELinux 过滤器，组合场景继续使用一次原生 Hook。另补齐 native_init 的库注册，修正缺失系统属性带默认值时的读取；验证器从真实已加载 ELF 调用 libselinux，避免 Android 私有库 namespace 限制导致没有基线。

## 各场景

| 用例 | 状态 |
|---|---|
| L00-capture | 通过 |
| L01-prepare | 通过 |
| L02-unscoped-permissive | 通过 |
| L03-all-off | 通过 |
| L04-selinux-only | 通过 |
| L05-all-on | 通过 |
| L06-enforcing-all-off | 通过 |
| L06-enforcing-baseline | 通过 |
| L07-enforcing-selinux-only | 通过 |
| L08-independent-A | 通过 |
| L09-independent-B | 通过 |
| L10-default-future-method | 通过 |
| L11-https-policy-isolation | 通过 |
| L12-ten-cold-starts | 通过 |
| L13-native-all-on | 通过 |
| L13-native-screenshot-only | 通过 |
| L13-native-selinux-only | 通过 |
| L99-restored | 通过 |
| M6-000000 | 通过 |
| M6-000001 | 通过 |
| M6-000010 | 通过 |
| M6-000011 | 通过 |
| M6-000100 | 通过 |
| M6-000101 | 通过 |
| M6-000110 | 通过 |
| M6-000111 | 通过 |
| M6-001000 | 通过 |
| M6-001001 | 通过 |
| M6-001010 | 通过 |
| M6-001011 | 通过 |
| M6-001100 | 通过 |
| M6-001101 | 通过 |
| M6-001110 | 通过 |
| M6-001111 | 通过 |
| M6-010000 | 通过 |
| M6-010001 | 通过 |
| M6-010010 | 通过 |
| M6-010011 | 通过 |
| M6-010100 | 通过 |
| M6-010101 | 通过 |
| M6-010110 | 通过 |
| M6-010111 | 通过 |
| M6-011000 | 通过 |
| M6-011001 | 通过 |
| M6-011010 | 通过 |
| M6-011011 | 通过 |
| M6-011100 | 通过 |
| M6-011101 | 通过 |
| M6-011110 | 通过 |
| M6-011111 | 通过 |
| M6-100000 | 通过 |
| M6-100001 | 通过 |
| M6-100010 | 通过 |
| M6-100011 | 通过 |
| M6-100100 | 通过 |
| M6-100101 | 通过 |
| M6-100110 | 通过 |
| M6-100111 | 通过 |
| M6-101000 | 通过 |
| M6-101001 | 通过 |
| M6-101010 | 通过 |
| M6-101011 | 通过 |
| M6-101100 | 通过 |
| M6-101101 | 通过 |
| M6-101110 | 通过 |
| M6-101111 | 通过 |
| M6-110000 | 通过 |
| M6-110001 | 通过 |
| M6-110010 | 通过 |
| M6-110011 | 通过 |
| M6-110100 | 通过 |
| M6-110101 | 通过 |
| M6-110110 | 通过 |
| M6-110111 | 通过 |
| M6-111000 | 通过 |
| M6-111001 | 通过 |
| M6-111010 | 通过 |
| M6-111011 | 通过 |
| M6-111100 | 通过 |
| M6-111101 | 通过 |
| M6-111110 | 通过 |
| M6-111111 | 通过 |

## 构建与文件

- AppStateShield-0.3.0.apk：c83795e10562feb54973afe33cbfeb9204dbe32265ef04a037062a1a9778a104
- AppStateVerifier-0.3.0.apk：6f268182355e98efab56b18ca47b86f04c338a3ef3e45f2c13bcb1c3afcd6d28

完整读数见同目录 selinux-0.3.0-results.json；步骤见 docs/TEST-MANUAL.md 的 L 节。
交付包也附有 AppStateShield-0.3.0-人工测试手册.md，包含相同步骤。
恢复结果见 L99；原始本机快照保持仓库外、600 权限。
