package io.github.lwtdzh.deviceprofile;

import java.security.SecureRandom;
import java.util.*;

/** Single field catalog for editing, validation and observation labels. */
public final class DeviceField {
    public final String id, group, zh, en, type, hint;
    public final boolean random;
    private DeviceField(String id, String group, String zh, String en, String type, String hint, boolean random) {
        this.id=id; this.group=group; this.zh=zh; this.en=en; this.type=type; this.hint=hint; this.random=random;
    }
    private static DeviceField f(String id,String group,String zh,String en,String type,String hint,boolean random) {
        return new DeviceField(id,group,zh,en,type,hint,random);
    }
    public static final List<DeviceField> ALL = Collections.unmodifiableList(Arrays.asList(
        f("brand","model","品牌","Brand","text","如 Xiaomi、vivo",false),
        f("manufacturer","model","制造商","Manufacturer","text","厂商名称",false),
        f("model","model","型号","Model","text","官方型号或手工值",false),
        f("device","model","设备代号","Device name","text","预设使用真实固件代号，也可手工修改",false),
        f("product","model","产品代号","Product","text","真实固件产品名或手工值",false),
        f("board","model","主板","Board","text","真实主板代号或手工值",false),
        f("hardware","model","硬件平台","Hardware","text","真实平台代号；不改变 CPU 指令集",false),
        f("fingerprint","model","固件指纹","Build fingerprint","text","预设使用原始固件指纹；不改变硬件认证",false),
        f("release","model","Android 版本文本","Android release text","text","不改变 SDK API 等级",false),
        f("incremental","model","固件版本","Build incremental","text","真实固件增量版本或手工值",false),
        f("imei","ids","IMEI · 卡槽 1","IMEI · slot 1","imei","15 位，含校验位",true),
        f("imei2","ids","IMEI · 卡槽 2","IMEI · slot 2","imei","与卡槽 1 分开生成",true),
        f("meid","ids","MEID","MEID","hex14","14 位十六进制",true),
        f("serial","ids","设备序列号","Serial","serial","6–32 位字母或数字",true),
        f("android_id","ids","Android ID","Android ID","hex16","16 位十六进制",true),
        f("oaid","ids","OAID","OAID","uuid","应用专用 UUID",true),
        f("vaid","ids","VAID","VAID","uuid","与 OAID 独立生成",true),
        f("aaid","ids","AAID","AAID","uuid","与 OAID 独立生成",true),
        f("gaid","ids","Google 广告 ID","Google advertising ID","uuid","标准 UUID",true),
        f("drm_id","ids","MediaDrm 设备 ID","MediaDrm device ID","hex64","32 字节；可能影响受保护内容",true),
        f("wifi_mac","network","网卡 MAC","Network MAC","mac","本地管理、单播地址",true),
        f("bt_mac","network","蓝牙地址","Bluetooth address","mac","本地管理、单播地址",true),
        f("ssid","network","Wi-Fi 名称","Wi-Fi SSID","text","只改读数，不切换网络",true),
        f("bssid","network","Wi-Fi BSSID","Wi-Fi BSSID","mac","接入点合成地址",true),
        f("imsi","network","IMSI","IMSI","imsi","MCC/MNC + 合成用户号",true),
        f("iccid","network","SIM 序列号","SIM serial / ICCID","iccid","19 或 20 位数字",true),
        f("phone","network","手机号读数","Phone number","phone","可留空，避免暴露原号码",true),
        f("operator","network","运营商名称","Operator name","text","如中国移动",false),
        f("latitude","location","纬度","Latitude","latitude","−90 至 90",false),
        f("longitude","location","经度","Longitude","longitude","−180 至 180",false),
        f("accuracy","location","定位精度","Location accuracy","accuracy","1–10000 米",false),
        f("mcc","network","MCC","MCC","mcc","3 位国家码",false),
        f("mnc","network","MNC","MNC","mnc","2 或 3 位网络码",false),
        f("lac","network","位置区 LAC","LAC","lac","0–65535；合成编号",true),
        f("cid","network","基站 CI / NCI","Cell ID","cid","0–268435455；合成 LTE 标识",true),
        f("tac","network","跟踪区 TAC","TAC","lac","0–65535；合成编号",true),
        f("pci","network","物理小区 PCI","PCI","pci","0–503；合成编号",true),
        f("signal","network","信号强度","Signal strength","signal","−140 至 −30 dBm；模拟读数",false),
        f("width","model","竖屏宽度","Portrait width","dimension","320–7680 像素",false),
        f("height","model","竖屏高度","Portrait height","dimension","320–7680 像素",false),
        f("density","model","逻辑密度","Logical densityDpi","density","120–960；不是物理 PPI",false),
        f("total_ram","environment","总内存","Total RAM","ram","1–64 GiB；可用量按比例显示，不改变实际内存",false),
        f("storage","environment","存储总容量","Total storage","storage","8–4096 GiB；数据分区剩余量按比例显示，不改变实际空间",false),
        f("timezone","environment","默认时区","Default time zone","timezone","如 Asia/Shanghai",false),
        f("language","environment","默认语言","Default language","language","BCP 47，如 zh-CN",false),
        f("hide_sensors","environment","隐藏传感器列表","Hide sensor list","bool","隐藏列表并拒绝 Java 监听；影响摇一摇等功能",false),
        f("hide_module_apps","environment","隐藏模块应用列表","Hide module applications","bool","仅过滤 PackageManager 中声明为 Xposed 模块的应用；不隐藏进程内注入",false)
    ));
    public static DeviceField find(String id) {
        for (DeviceField f : ALL) if (f.id.equals(id)) return f;
        return null;
    }
    public String validate(String input) {
        String s=input==null?"":input.trim();
        if (s.length()>256 || s.indexOf('\n')>=0 || s.indexOf('\0')>=0) return "最多 256 个字符，不能换行";
        switch (type) {
            case "imei": return s.matches("\\d{15}") && luhn(s)==0 ? null : "请输入含正确校验位的 15 位 IMEI";
            case "hex14": return s.matches("[0-9a-fA-F]{14}") ? null : "需要 14 位十六进制";
            case "hex16": return s.matches("[0-9a-fA-F]{16}") ? null : "需要 16 位十六进制";
            case "hex64": return s.matches("[0-9a-fA-F]{64}") ? null : "需要 64 位十六进制";
            case "serial": return s.matches("[a-zA-Z0-9]{6,32}") ? null : "需要 6–32 位字母或数字";
            case "uuid": try { return UUID.fromString(s).toString().equalsIgnoreCase(s) ? null : "请输入标准 UUID"; }
                catch (RuntimeException e) { return "请输入标准 UUID"; }
            case "mac": return s.matches("(?i)[0-9a-f]{2}(:[0-9a-f]{2}){5}") ? null : "格式为 02:12:34:56:78:9A";
            case "imsi": return s.matches("\\d{14,15}") ? null : "需要 14 或 15 位数字";
            case "iccid": return s.matches("\\d{19,20}") ? null : "需要 19 或 20 位数字";
            case "phone": return s.isEmpty() || s.matches("\\+?\\d{5,16}") ? null : "手机号可留空，或输入 5–16 位数字";
            case "mcc": return s.matches("\\d{3}") ? null : "需要 3 位数字";
            case "mnc": return s.matches("\\d{2,3}") ? null : "需要 2 或 3 位数字";
            case "bool": return "true".equals(s) || "false".equals(s) ? null : "需要 true 或 false";
            case "timezone": return Arrays.asList(TimeZone.getAvailableIDs()).contains(s) ? null : "未知时区";
            case "language": return s.matches("[a-zA-Z]{2,3}(-[a-zA-Z0-9]{2,8})*") && !Locale.forLanguageTag(s).getLanguage().isEmpty() ? null : "请输入 BCP 47 语言码";
            case "text":
                int max=id.equals("ssid")?32:id.equals("fingerprint")?256:91;
                return s.isEmpty()?"请填写内容":s.getBytes(java.nio.charset.StandardCharsets.UTF_8).length>max?
                    "最多 "+max+" 个 UTF-8 字节，需与系统读取接口一致":null;
            default:
                double lo=0,hi=0;
                switch(type) {
                    case "lac": hi=65535; break; case "cid": hi=268435455; break; case "pci": hi=503; break;
                    case "signal": lo=-140; hi=-30; break; case "latitude": lo=-90; hi=90; break;
                    case "longitude": lo=-180; hi=180; break; case "accuracy": lo=1; hi=10000; break;
                    case "dimension": lo=320; hi=7680; break; case "density": lo=120; hi=960; break;
                    case "ram": lo=1; hi=64; break; case "storage": lo=8; hi=4096; break;
                    default: return "未知字段";
                }
                try {
                    double n=Double.parseDouble(s);
                    boolean fractional=type.equals("latitude") || type.equals("longitude") || type.equals("accuracy");
                    return Double.isFinite(n) && n>=lo && n<=hi && (fractional || n==Math.rint(n)) ? null : "允许范围："+lo+" 至 "+hi;
                } catch(RuntimeException e) { return "请输入数字"; }
        }
    }
    private static final SecureRandom RNG=new SecureRandom();
    private static String digits(int n) { StringBuilder s=new StringBuilder(); for(int i=0;i<n;i++) s.append(RNG.nextInt(10)); return s.toString(); }
    private static String hex(int n) { StringBuilder s=new StringBuilder(); for(int i=0;i<n;i++) s.append("0123456789abcdef".charAt(RNG.nextInt(16))); return s.toString(); }
    public static int luhn(String s) {
        int sum=0; boolean twice=false;
        for(int i=s.length()-1;i>=0;i--){int n=s.charAt(i)-'0'; if(twice){n*=2;if(n>9)n-=9;}sum+=n;twice=!twice;}
        return sum%10;
    }
    public String generate() {
        switch(type) {
            case "imei": String s="99"+digits(12); return s+((10-luhn(s+"0"))%10);
            case "hex14": return hex(14); case "hex16": return hex(16); case "hex64": return hex(64);
            case "serial": return hex(16).toUpperCase(Locale.ROOT);
            case "uuid": return UUID.randomUUID().toString();
            case "mac": return "02:"+hex(2)+":"+hex(2)+":"+hex(2)+":"+hex(2)+":"+hex(2);
            case "imsi": return "46000"+digits(10); case "iccid": return "898600"+digits(13);
            case "phone": return ""; case "lac": return String.valueOf(RNG.nextInt(60000)+1);
            case "cid": return String.valueOf(RNG.nextInt(268435454)+1);
            case "pci": return String.valueOf(RNG.nextInt(504));
            default: return id.equals("ssid")?"Home-"+hex(6):"";
        }
    }
    public static String groupName(String id, boolean zh) {
        switch(id) {
            case "model": return zh?"机型与系统":"Model & system";
            case "ids": return zh?"设备标识":"Device identifiers";
            case "network": return zh?"网络与基站":"Network & cell";
            case "location": return zh?"位置":"Location";
            default: return zh?"其他环境":"Other environment";
        }
    }
}
