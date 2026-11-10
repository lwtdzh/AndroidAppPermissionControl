# 截图检测软件：使用与验证

这是独立的 Android 项目 `ScreenshotDetector`，源码在 `app/`。通用说明见[集合 README](../README.md)、[AGENTS.md](../AGENTS.md) 和[共享工作流 Skill](../.trae/skills/android-permission-workflow/SKILL.md)。

与防护模块、Probe 的关系及共用测试条件统一记录在 [PROJECT-RELATIONSHIPS.md](../PROJECT-RELATIONSHIPS.md)。新增检测入口或修改测试夹具时请检查对应防护规则与相关脚本。

截图防护代码属于另一个独立项目 [module-screenshot-shield](../module-screenshot-shield/README.md)，自动化 Probe 属于 [module-screenshot-probe](../module-screenshot-probe/README.md)。

## 构建

直接在 Android Studio 中打开本目录，或在本目录运行：

```sh
./gradlew :app:assembleRelease
```

使用 JDK 17、SDK 36、NDK `29.0.14206865` 和 CMake `3.22.1`。APK 输出到 `app/build/outputs/apk/release/app-release-unsigned.apk`。共享签名脚本为 `../scripts/sign-apk.py`；原包名、版本与签名身份保持不变。

模块安装包：`ScreenshotShield-0.1.4.apk`。检测安装包：`ScreenshotDetector-0.1.1.apk`。

模块 0.1.4 的 native 兼容性修复后，已重新通过 [13 类真实截图信号检查](verification/detector-expanded-0.1.4.json) 和 [真实选图授权读取检查](verification/detector-read-0.1.4.json)。截图信号被拦截，普通图片读取保留；实测环境为 Android 16 ARM64 模拟器与 Vector 2.2。

模块继续隐藏桌面图标，说明页可从 Vector/Xposed 进入。检测软件保留桌面图标。

## 怎样比较

1. 在 Vector 中启用模块，先不要把“截图检测日志”加入作用域。
2. 打开检测软件。默认同时监听全部入口，也可通过下拉列表单独选择。
3. 根据要测试的入口授予权限。相册查询要允许所有照片；文件测试可开启所有文件访问；通知和无障碍要在系统设置中启用对应服务。
4. 回到检测页面，等待各入口完成准备，然后用手机的系统截图操作截图，查看哪些来源出现日志。
5. 将检测软件加入模块作用域，强行停止并重新打开，重复相同操作。

一个入口只有在保护前能收到信号时，保护后的零日志才有比较意义。照片权限不足、服务未连接或入口不可用会直接显示在页面上。

“清空日志”只清空计数和界面记录。“重新开始监听”会重新建立已有图片、通知和窗口的基线。切换到其他 App 时暂停记录；界面最多保留 200 条。

## 18 个自动入口

| 入口 | 实际执行 |
| --- | --- |
| 官方回调 | `Activity.registerScreenCaptureCallback` |
| 直接 Binder | 单独注册 `IScreenCaptureObserver`，发送当前系统的 AIDL transaction；读取已安装 framework Dex 中的常量，避免依赖固定编号或放宽隐藏 API 策略 |
| MediaStore 变化通知 | 独立 `ContentObserver`，收到变化后查询新截图 |
| MediaStore Bundle 轮询 | 每秒独立查询一次，与变化通知分别记日志 |
| MediaStore 旧式查询 | 独立使用 selection、projection、sortOrder |
| ContentProviderClient 查询 | 独立通过 provider client 查询 |
| Java FileObserver | 监听图片父目录与常见截图目录的写入完成和移动事件 |
| Java 文件元数据 | 轮询目录列表、文件类型和大小 |
| native inotify | 在 `fcntl` 复制的 fd 上添加 watch，通过真实 `read` 读取事件 |
| native libc 元数据 | `opendir`、`readdir`、`stat` |
| libc syscall 元数据 | `syscall` 的 `openat`、`getdents64`、`statx` |
| 动态广播 | 注册预设 action，允许添加一个额外 action |
| 静态广播 | Manifest 注册预设 action |
| 剪贴板 | 变化监听、图片描述和可读取的 URI 元数据 |
| 通知回调 / 排名 | 真实通知监听服务回调；排名中的 key 需要配合可识别通知元数据判断 |
| 活动 / 延后通知列表 | 独立读取 active 与 snoozed 列表 |
| 无障碍事件 | 真实系统服务传来的事件 |
| 无障碍节点 / 焦点 / 窗口 | 读取根节点、两种焦点和交互窗口；已有窗口先作基线 |

文件轮询扫描 `DCIM`、`Pictures`、`Download` 及其带截图标识的直接子目录。Java/native 文件检测只认带截图名称或目录标识的 PNG、JPEG、WebP、HEIC；不会把写入中的临时文件当成已保存图片。相册每次查询最多检查最近 256 行。

广播预设是候选 action，不代表所有 ROM 都会发送。无法通配订阅任意未知 action；额外 action 需要填入实际名称，其末段还需包含可识别的截图标识。通知、无障碍和剪贴板也依赖系统操作确实提供相应信息。剪贴板读取受 Android 前台访问限制。

## 选图读取检查

点“选择图片检查读取”，在系统文件选择器中实际选一张图片。检查使用选图器给出的 URI 授权；结果会单列为读取检查，不计入截图信号数。

- 文档 ID 和仅文件名查询。
- ContentResolver 输入流、AssetFileDescriptor、文件描述符。
- ContentProviderClient 文件描述符。
- 系统缩略图能否取得。
- native open/proc fd 别名、stat、read、pread、readv、mmap、fcntl 副本读取、fstat、syscall statx。

输入流和 native 读取只检查少量字节能否取得，缩略图只检查能否返回，不做 OCR、像素分析或相册内容扫描。没有拿到 fd 时，对应 native 检查也会显示不可取得。

“不可取得”可能来自模块、权限或 provider 本身不支持，需用同一图片保护前后的结果比较。推荐再选一张普通图片作对照。

## 已验证的结果

专用 Android 16 ARM64 模拟器、Vector 2.2、模块 0.1.3、检测软件 0.1.1：

- 实际 SystemUI 截图同时触发 13 个入口：官方 API、直接 Binder、4 个相册入口、Java 文件监听与元数据、3 个 native 文件入口、无障碍事件与节点。开启作用域后，这些信号为零，两次操作均由 SystemUI 保存了新截图。
- 动态、静态广播分别使用真正交付的测试消息验证：保护前到达，保护后被抑制。消息是测试夹具，没有声称该 ROM 的截图操作发送了这些 action。
- 独立检测软件发现 0.1.2 中动态广播实际交付仍能到达；0.1.3 在注册时 hook 接收器具体 `onReceive`，实际交付对照已通过。
- 系统选图器实际授权的截图、普通图片完成四组读取对照：截图保护前可查询、打开和取得缩略图，保护后不可取得；普通图片保护前后仍可取得。模块先拦住截图的文件描述符获取，因此该组 native fd 检查的不可取得不单独证明每个 native hook；已有 fd 的逐项拦截由独立 Probe 测试验证。
- 当前 ROM 在保护前也拒绝经 `/proc/self/fd` 重新打开选图器的 fd，该项在界面显示不可取得，没有算成模块保护成功。
- 自动监听不记录文件名、路径、URI、通知正文或其他界面文本；直接 Binder 对照使用默认隐藏 API 策略。

这次真实截图没有触发截图剪贴板或新的可识别截图通知，因此这两类入口的“零信号”没有算作本次真实截图防护验证。不同 ROM、旧 Android 或其他 CPU 架构仍需单独运行；四种 native 架构编译通过不等于全部实机通过。

既有通知/剪贴板/无障碍构造元数据的模块验证，保留在 `../module-screenshot-shield/verification/`，其证据性质见 [COVERAGE-AUDIT.md](../module-screenshot-shield/COVERAGE-AUDIT.md)。此次新增检测软件的运行记录为 `verification/detector-expanded.json`。

选图读取记录为 `verification/detector-read.json`，0.1.3 的普通文件、图片、广播与既有 fd 对照为 `../module-screenshot-shield/verification/integration-0.1.3.json`。从本目录依次执行以下命令，可以重建夹具并重复选图读取验证；这些脚本均使用专用测试模拟器。

```sh
../module-screenshot-probe/gradlew -p ../module-screenshot-probe :app:assembleDebug
python3 ../module-screenshot-probe/scripts/emulator-test.py --serial emulator-5584 \
  --module-apk /path/to/ScreenshotShield-0.1.4.apk --output /tmp/integration.json
python3 scripts/detector-test.py
python3 scripts/detector-read-test.py
```

2026-11-08 已在 vivo V2419A（Android 16、ARM64）安装模块 0.1.3 和检测软件 0.1.1，并完成通知与剪贴板对照：

- 保护前，实际投递的测试通知触发通知回调 2 条、通知列表 2 条；引用本次已保存截图的图片 ClipData 触发剪贴板 1 条。
- 将检测软件加入模块作用域并重启后，系统仍保存了测试通知和图片剪贴板，三种检测日志均为 0。
- 这台手机的普通系统截图没有自动写入图片剪贴板，也没有新增可识别的截图通知。因此上述验证使用明确标注的测试通知和图片剪贴板，不将普通截图的零信号当作拦截证据。

测试后已恢复原剪贴板、作用域和通知授权；原有通知监听、无障碍设置及应用语言保持原样，测试通知和手机临时文件已清理。记录见 `verification/vivo-notification-clipboard.json`。

拆成独立 Android 项目后，选图读取脚本已重新运行通过，补充记录见 [verification/layout-read-checks.json](verification/layout-read-checks.json)。
