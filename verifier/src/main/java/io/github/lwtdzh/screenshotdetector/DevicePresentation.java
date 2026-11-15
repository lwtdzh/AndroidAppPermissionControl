package io.github.lwtdzh.screenshotdetector;

import org.json.JSONObject;
import java.util.Locale;

/** Human-readable display of observations, never a substitution from saved profiles. */
final class DevicePresentation {
    private static String t(boolean zh,String cn,String en){return zh?cn:en;}
    static String overview(JSONObject read,String id,boolean zh){
        if(read!=null&&"SecurityException".equals(read.optString("error")))
            return t(zh,"系统限制 · 详情查看原因","System restricted · see details");
        return value(read,id,zh);
    }
    static String value(JSONObject read,String id,boolean zh){
        if(read==null)return t(zh,"正在读取…","Reading…");
        if(read.has("error")){
            String error=read.optString("error");
            switch(error){
                case "SecurityException":
                    return t(zh,"系统拒绝读取：权限不足或受隐私限制","System denied access: permission or privacy restriction")+
                        (java.util.Arrays.asList("imei","imei2","device_id","meid","serial","imsi","iccid").contains(id)?
                            t(zh,"。Android 10+ 的真实标识通常还需特权或运营商权限",
                                ". Real identifiers on Android 10+ usually need privileged or carrier access"):"");
                case "ClassNotFoundException":case "NoSuchMethodException":
                    return t(zh,"未提供对应厂商服务或 SDK","OEM service or SDK is unavailable");
                case "TimeoutException":
                    return t(zh,"读取超时，稍后自动重试","Read timed out; retries automatically");
                default:return t(zh,"读取失败：","Read failed: ")+error;
            }
        }
        Object observed=read.opt("value");
        if(observed==null||observed==JSONObject.NULL||observed.toString().isEmpty())
            return t(zh,"无数据：接口返回空值","No data: API returned an empty value");
        String value=observed.toString();
        if(id.startsWith("sim_state")||id.equals("sim_card_state")||id.equals("sim_application_state")){
            switch(value){
                case "0":return t(zh,"未知（0）","Unknown (0)");case "1":return t(zh,"无卡（1）","Absent (1)");
                case "5":return t(zh,"已就绪（5）","Ready (5)");case "10":return t(zh,"已加载（10）","Loaded (10)");
                case "11":return t(zh,"有卡（11）","Present (11)");default:return value;
            }
        }
        if(id.equals("has_sim"))return "true".equals(value)?t(zh,"有 SIM 卡","SIM present"):t(zh,"无 SIM 卡","No SIM");
        if(id.equals("network_type")||id.equals("voice_network_type"))
            return "13".equals(value)?"LTE (13)":"0".equals(value)?t(zh,"未知 / 无移动网络（0）","Unknown / no mobile network (0)"):value;
        if(id.equals("data_state"))return "2".equals(value)?t(zh,"已连接（2）","Connected (2)"):
            "0".equals(value)?t(zh,"未连接（0）","Disconnected (0)"):value;
        if(("wifi_mac".equals(id)||"bt_mac".equals(id))&&"02:00:00:00:00:00".equals(value))
            return value+t(zh," · 系统隐私占位地址"," · system privacy placeholder");
        if("serial".equals(id)&&"unknown".equalsIgnoreCase(value))
            return t(zh,"unknown · 系统未提供序列号","unknown · serial not provided by the system");
        if(("total_ram".equals(id)||"storage".equals(id))&&observed instanceof Number)
            return String.format(Locale.getDefault(),"%.2f GiB · %s bytes",((Number)observed).doubleValue()/1073741824d,value);
        if("hide_sensors".equals(id))return value+t(zh," 个可见传感器"," visible sensors");
        if("hide_module_apps".equals(id))return value+t(zh," 个可见模块应用"," visible module applications");
        return value;
    }
}
