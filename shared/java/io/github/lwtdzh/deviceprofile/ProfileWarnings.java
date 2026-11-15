package io.github.lwtdzh.deviceprofile;

import java.util.*;

/** Draft observations, not a claim about any commercial risk verdict. */
public final class ProfileWarnings {
    public static List<String> messages(DeviceProfile p,String hostRelease,boolean zh) {
        List<String> out=new ArrayList<>();
        if(!p.enabled)return out;
        String raw=p.get("fingerprint");
        BuildFingerprint f=BuildFingerprint.parse(raw);
        if(raw!=null&&f==null)out.add(zh?"固件指纹格式不完整，无法同步编译编号和类型。":
            "The fingerprint format is incomplete; build ID and type cannot follow it.");
        if(f!=null){
            String[][] related={{"brand",f.brand},{"product",f.product},{"device",f.device},
                {"release",f.release},{"incremental",f.incremental}};
            for(String[] pair:related){
                String value=p.get(pair[0]);
                if(value!=null&&!value.equals(pair[1])){
                    DeviceField field=DeviceField.find(pair[0]);
                    out.add(zh?field.zh+"与固件指纹不一致。":field.en+" differs from the fingerprint.");
                }
            }
        }
        String release=p.get("release");
        if(release==null&&f!=null)release=f.release;
        if(release!=null&&hostRelease!=null&&!major(release).equals(major(hostRelease)))
            out.add(zh?"预设 Android "+release+"，本机 Android "+hostRelease+"；实际 API 和内核不会跟着改变。":
                "Profile Android "+release+", phone Android "+hostRelease+"; actual APIs and kernel stay unchanged.");
        if("true".equals(p.get("hide_sensors")))out.add(zh?"隐藏全部传感器可能影响扫码、运动感知，也可能被视为异常。":
            "Hiding all sensors may affect scanning and motion sensing, and may look abnormal.");
        if(p.noSim())out.add(zh?"当前模拟无 SIM 卡；运营商一键登录可能不可用，可尝试密码或短信登录。":
            "No SIM is simulated; carrier one-tap login may fail. Password or SMS login may still work.");
        else if(p.simulatedSim())out.add(zh?"模拟 SIM 信息不会建立真实运营商通道；一键登录仍可能失败。":
            "A simulated SIM does not create a carrier channel; one-tap login may still fail.");
        return Collections.unmodifiableList(out);
    }
    private static String major(String value){return value.split("\\.",2)[0];}
    private ProfileWarnings(){}
}
