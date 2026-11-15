# 旧属性接口修复与指纹验证

0.4.4 修复两个已确认问题：旧 read 返回截断属性名，过滤器因此查不到预设；旧 get/read 把长预设指纹截成半段。替换短值后，旧值尾部也可能留在输出缓冲区，现一并清理。

指纹字段的配置校验允许完整 256 个 UTF-8 字节，其他普通文本字段仍保留原长度限制。超过 91 字节的有效手工指纹能保存和加载，不再因为旧接口长度校验被拒绝为关闭档案。

read 继续让系统填充调用方的名称缓冲区，再通过该 Hook 所属库的原始 callback 取得完整属性名称。过滤器按完整名称精确查表，避免前 31 字节相同的属性混淆，也支持调用方不需要名称、传入 nullptr 的读法。

get/read 的值缓冲区仍按 Android 的 92 字节约定使用。预设只读值达到 92 字节时返回：

```text
Must use __system_property_read_callback() to read
```

Java 和 callback 继续返回完整预设指纹。每次替换清零整个旧接口值缓冲区，再复制受控返回值，避免结束符后残留本机原指纹；不扩大调用方缓冲区。

devicestate 独立属性 Hook，以及 developerstate/selinuxstate 共用的属性 Hook，都调用同一辅助函数。机器和字段关闭时保持系统原读数；允许读取的原值不做格式改写。

测试分为本地 native sanitizer 边界检查和 Android 16 ARM64 / Vector 专用模拟器检查。字段包括根、system、system_ext、vendor、product、odm 六个指纹，以及 system_ext 的 manufacturer、device、name 三项长属性名。包含 get/read/callback、空名称 read、Java/Build、返回长度、缓冲区完整内容和前后哨兵；同进程测试 91/92/128/256 字节与长值换短值，检查字段和机器关闭后的还原。

本次修改共享 native 属性 Hook，因此完整执行六项开关的 64 组合。每个组合同时检查实际截图文件夹具、VPN、代理、开发者选项、USB 调试、SELinux 的真实模式与原生文件对照，以及机器伪装指纹。合成截图文件不是 SystemUI 截图事件；未改变截图信号 Hook，不将夹具结果宣称为真实截图验证。

修复保证范围为成功安装的上述读取适配器中，已选择且配置有效的指纹返回及值缓冲区。直接读取 prop_info/属性区内存、未注入进程、未适配的属性、保留的外部 Hook 入口和内核信息仍不属于这次验证；callback 的原始 serial 元数据没有虚拟化。不会声称所有任意检测方式都已被屏蔽。

源码：shared/native/property-read.h，app/src/main/cpp/devicestate.cpp、developerstate.cpp、selinuxstate.cpp。执行器：scripts/property-repair-test.py。报告：verification/property-repair-0.4.4-results.json。
