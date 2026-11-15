# 只读设备属性对象：实现与限制

0.4.6 在已有设备 native 层内补充属性对象适配。0.4.5 的 find 返回原 prop_info，read/callback 只替换文本，callback 继续使用原 serial。现在为选中的 ro.* 设备属性创建不可变的只读对象；find、foreach、find_nth 返回同一名称/值对应的对象，原始 Bionic serial 直接读取其头部。

主入口仍为 DeviceRuntime.apply → nativeUpdate。每个 getter 使用进程内不可变配置快照，不增加 Binder 读取。机器伪装默认关闭，六项 Methods、Provider 权限、Vector 作用域、机型预设和界面操作均保留。

## 对象布局与生命周期

头部为 96 字节：serial 位于偏移 0，92 字节兼容槽位于偏移 4，名称位于偏移 96。短值 serial 高位记录值的长度；92 字节及以上的只读值设置 long flag，兼容槽保留 Android 的提示文本，偏移 60 的相对地址指向完整值。长值的 serial 高位是兼容提示长度 50，不是完整指纹的长度。

对象写入 memfd 共享映射后撤掉写映射，加上写入、尺寸和 seal 修改限制，再只保留 PROT_READ 的私有文件映射并关闭文件描述符。该环境拒绝 seal 后重新创建共享映射，实际使用私有文件映射。Bionic 的 shared futex 可以使用它的文件页等待键；只读私有匿名映射会在此处产生错误，使系统等待循环空转。按完整名称和值复用对象，已经返回给应用的对象不改写、不释放；应用缓存的旧只读对象保留旧伪装值。配置更新后重新 find 得到新对象，既有原对象经本模块 read/callback 按当前选择映射。机器或字段关闭后重新 find 恢复系统对象。静态字段和应用自身缓存仍需要冷启动。

初始化先用原始 callback 核对已知短属性的名称、值和头部，再索引原始对象地址。未知指针不根据猜测的内存布局识别；已创建对象按地址所有权识别，不能靠“文本等于某次预设”识别。后者会在真实值碰巧等于旧预设时冻结错误读数。

foreach 保留系统顺序、错误码及未选属性，仅替换对应对象，再按名称顺序补充系统原本缺少的选中 ro.* 属性。find_nth 保留系统索引，在末尾提供这些补充项。没有虚拟化可变属性或全局属性区更新序号。

## 本 APK 内部的共享读取

developerstate 或 selinuxstate 已拥有 read/callback 时，devicestate 注册同一 HandleAdapter，先映射指针，再调用该读取层的原始入口。属于设备层的只读对象直接使用其中的最终值和 serial，避免重新对旧缓存值套用当前文本过滤器。未选中的调试、SELinux 属性继续走原来的过滤逻辑。

旧 read 保持名称缓冲区语义，并清理整个 92 字节值缓冲区。callback 使用完整名称、完整值及对象的 serial。没有强行 Hook 很短的 serial 函数；继续保留 16 字节入口大小检查和外部跳转守卫。native_init 不进行 dlopen，不改变系统属性映射。

DeviceRuntime.status 新增 deviceNativeObjects，表示布局核验和三个对象入口安装是否成功。平台版本超过已核验的 API 36、布局不符、入口无法安装或对象分配失败时报告不可用，原有文本适配继续保留。这个状态不是“检测全部通过”。

## 仍未覆盖的读取

- 应用自行映射系统属性区并使用自己的解析器；模块启用前已取得原对象并直接读取其原始内存。
- 检查对象映射来源；memfd 只读映射与系统属性共享映射仍可区分。
- 全局属性区更新通知、已经缓存的不可变对象/Java 静态值；本次只核验对象的零超时等待。
- 未选中的可变属性，以及 debug/SELinux 自己过滤的属性对象元数据；它们保留原过滤逻辑，本次没有统一虚拟化所有属性。
- 未注入或被 Vector 排除的隔离进程、exec 后的地址空间、任意直接 SVC、代码完整性和硬件/服务端证明。
- vivo 和其他 ABI 的运行兼容性；四 ABI 编译不等于四 ABI 实机测试。

这些问题各有入口和权限要求。模块协作调研解释 Zygisk Assistant、HMA-OSS、SUSFS/LKM 能补什么，不把它们当作商业应用登录的保证。

## 复现与测试选择

执行 scripts/build-all.sh 并签名、审计后，在专用 ScreenshotShield_API36 / emulator-5584 执行 scripts/property-object-test.py selected；对应原始内存、serial、缺失属性、枚举、旧缓存、同进程更新/关闭和共享读取。只有已建立原快照才执行 prepare；中断保留结果和快照。

共享 native 层本次改变，因此稳定后执行一次 scripts/property-object-test.py matrix 的 64 组合。最后执行 scripts/property-object-test.py restore。本地 PropertyViewTest.cpp 使用 AddressSanitizer/UndefinedBehaviorSanitizer 检查布局、长度、不可变生命周期和并发复用。上轮界面与纯逻辑结果仍保留原版本归属。

当前报告和失败观察保存于 verification/property-objects-0.4.6-results.json；构建输入、APK 校验和恢复结果随交付包保存。报告的最终通过项以实际执行数据为准。

本次 10 项定向检查及 64 组合已通过。组合执行在 21 项后遭遇模拟器电话服务失效导致的 system_server Binder 线程耗尽和 Watchdog 重启；源码与 APK 未改，仅为剩余用例的档案增加现有 serial 字段，避免无关的 Build.getSerial 权限读取。21 项保持原样，43 项续跑；执行器两个版本、失败、系统 ANR 及档案修订保留。最终恢复原包、完整数据、设置、作用域、授权/语言，解除 ADB root 并关闭专用模拟器。该结果不包括无线电服务修复或 vivo/商业应用登录。
