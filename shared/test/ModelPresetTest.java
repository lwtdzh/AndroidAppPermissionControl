import io.github.lwtdzh.deviceprofile.*;
import java.util.*;

public final class ModelPresetTest {
    private static int checks;
    private static void check(boolean ok,String reason){if(!ok)throw new AssertionError(reason);checks++;}
    public static void main(String[] args)throws Exception{
        DeviceProfile x=DeviceProfile.preset("xiaomi-14"),v=DeviceProfile.preset("vivo-x200-pro-mini");
        check(x.values.get("device").equals("houji")&&x.values.get("product").equals("houji_global"),"Stock Xiaomi names differ");
        check(x.values.get("board").equals("houji")&&x.values.get("release").equals("15"),"Stock Xiaomi board/release");
        check(x.values.get("hardware").equals("qcom"),"Xiaomi hardware verified in official OTA bootconfig");
        check(ModelPresets.missing("xiaomi-14","model").isEmpty(),"All Xiaomi model fields verified");
        check(x.values.get("fingerprint").equals("Xiaomi/houji_global/houji:15/AQ3A.240627.003/OS2.0.201.0.VNCMIXM:user/release-keys"),"Original official OTA fingerprint");
        check(x.values.get("density").equals("480")&&x.values.get("total_ram").equals("12"),"Xiaomi density and memory");
        check(v.values.get("device").equals("PD2419")&&v.values.get("product").equals("PD2419"),"Captured vivo product identities");
        check(v.values.get("model").equals("V2419A")&&v.values.get("board").equals("k6991v1_64"),"Captured vivo model and board");
        check(v.values.get("hardware").equals("mt6991")&&v.values.get("release").equals("16"),"Captured vivo hardware and version");
        check(v.values.get("fingerprint").equals("vivo/PD2419/PD2419:16/BP2A.250605.031.A3_V000L1/compiler261012170621:user/release-keys"),"Captured vivo fingerprint");
        check(v.values.get("width").equals("1080")&&v.values.get("height").equals("2344")&&v.values.get("density").equals("480"),"Actual wm dimensions and logical density");
        check(ModelPresets.missing("vivo-x200-pro-mini","model").isEmpty(),"All vivo model fields observed");
        check(ModelPresets.values("oppo-x9s").isEmpty(),"OPPO preset removed");
        for(String name:new String[]{"xiaomi-14","vivo-x200-pro-mini"}){
            DeviceProfile p=DeviceProfile.preset(name);
            check(!p.locationEnabled&&p.networkMode.equals("no_sim"),"Existing default gates");
            for(Map.Entry<String,String> e:p.values.entrySet()){
                check(!e.getValue().contains("privacy_")&&!e.getValue().contains("PRIVATE.")&&!e.getValue().startsWith("Private-"),"No obvious placeholders");
                check(DeviceField.find(e.getKey()).validate(e.getValue())==null,"Valid preset "+e.getKey());
            }
            Map<String,String> model=DevicePackets.group("model",name);
            for(int i=0;i<4;i++)check(model.equals(DevicePackets.group("model",name)),"Repeated model refresh stable");
            check(!p.values.get("imei").equals(DeviceProfile.preset(name).values.get("imei")),"IDs can still regenerate");
        }
        check(ModelPresets.property(x,"ro.product.vendor.device","device").equals("mivendor"),"Vendor uses its real partition identity");
        check(ModelPresets.property(x,"ro.product.odm.name","product").equals("houji_global"),"ODM product name");
        check(ModelPresets.property(x,"ro.product.system_ext.manufacturer","manufacturer").equals("QUALCOMM"),"System extension manufacturer");
        check(ModelPresets.property(x,"ro.vendor.build.version.release","release").equals("14"),"Vendor release differs legitimately");
        check(ModelPresets.property(x,"ro.vendor.build.fingerprint","fingerprint").equals("Xiaomi/mivendor_sm8650_global/mivendor:14/UKQ1.240523.001/OS2.0.201.0.VNCMIXM:user/release-keys"),"Actual Xiaomi vendor fingerprint");
        check(ModelPresets.property(x,"ro.system.build.fingerprint","fingerprint").equals("qti/missi/missi:15/AQ3A.240627.003/OS2.0.201.0.VNCMIXM:user/release-keys"),"Actual Xiaomi system fingerprint");
        check(ModelPresets.property(x,"ro.build.fingerprint","fingerprint").equals(x.values.get("fingerprint")),"Global fingerprint");
        check(ModelPresets.property(v,"ro.product.vendor.device","device").equals("PD2415"),"Actual vivo vendor partition identity");
        check(ModelPresets.property(v,"ro.product.system_ext.device","device").equals("mssi_64_64only_cn_armv82"),"Actual vivo system extension identity");
        check(ModelPresets.property(v,"ro.vendor.build.version.release","release").equals("15"),"Actual vivo vendor Android version");
        check(ModelPresets.property(v,"ro.odm.build.version.release","release").equals(""),"Preserve actually empty ODM version");
        check(ModelPresets.property(v,"ro.sf.lcd_density","density").equals("560"),"Keep property density distinct from wm density");
        check(ModelPresets.property(v,"ro.build.fingerprint","fingerprint").equals(v.values.get("fingerprint")),"Actual vivo root fingerprint");
        DeviceProfile off=v.with(false,2,v.values,v.selected,v.preset);
        check(ModelPresets.property(off,"ro.product.vendor.device","device")==null,"Master off restores partition reads");
        Set<String> none=new LinkedHashSet<>(v.selected);none.remove("device");
        check(ModelPresets.property(v.with(true,3,v.values,none,v.preset),"ro.product.vendor.device","device")==null,"Field off restores partition reads");
        Map<String,String> changed=new LinkedHashMap<>(x.values);changed.put("device","custom-device");
        check(ModelPresets.property(x.with(true,1,changed,x.selected,x.preset),"ro.product.vendor.device","device").equals("custom-device"),"Manual override is honored");
        Map<String,String> legacy=new LinkedHashMap<>(x.values);
        legacy.put("device","privacy_x14_123456");legacy.put("product","privacy_x14_123456");
        legacy.put("board","privacy_board");legacy.put("hardware","privacy_platform");legacy.put("release","16");
        legacy.put("fingerprint","Xiaomi/privacy_x14_123456/privacy_x14_123456:16/PRIVATE/PRIVATE.12345678:user/release-keys");
        legacy.put("incremental","PRIVATE.12345678");legacy.put("density","420");legacy.put("total_ram","8");
        legacy.put("ssid","Private-123abc");legacy.put("future_value","KEEP");
        Set<String> selected=new LinkedHashSet<>(x.selected);selected.add("hardware");selected.add("future_value");
        String original=new DeviceProfile(true,1,x.preset,legacy,selected).json();
        DeviceProfile migrated=DeviceProfile.parse(original);
        check(migrated.values.get("device").equals("houji")&&migrated.values.get("product").equals("houji_global"),"Recognized legacy names migrate");
        check(migrated.values.get("release").equals("15")&&migrated.values.get("density").equals("480"),"Legacy version/density corrected");
        check(migrated.values.get("fingerprint").equals(x.values.get("fingerprint")),"Legacy fingerprint corrected");
        check(migrated.values.get("hardware").equals("qcom"),"Legacy hardware placeholder replaced with verified value");
        check(migrated.values.get("ssid").equals("Home-123abc"),"Deterministic SSID migration, no random read");
        check(migrated.values.get("imei").equals(legacy.get("imei"))&&migrated.values.get("future_value").equals("KEEP"),"Retain IDs and future values");
        check(DeviceProfile.parse(original).json().equals(migrated.json()),"Repeated parsing is stable");
        Map<String,String> manual=new LinkedHashMap<>(x.values);manual.put("device","my-device");manual.put("board","my-board");manual.put("hardware","my-hardware");
        DeviceProfile p=new DeviceProfile(true,1,x.preset,manual,new LinkedHashSet<>(manual.keySet()));
        check(DeviceProfile.parse(p.json()).values.equals(manual),"Do not overwrite user's manual profile");
        Map<String,String> retired=new LinkedHashMap<>(v.values);
        retired.put("device","privacy_x9s_123456");retired.put("product","privacy_x9s_123456");
        retired.put("board","privacy_board");retired.put("hardware","privacy_platform");
        retired.put("incremental","PRIVATE.12345678");
        retired.put("fingerprint","OPPO/privacy_x9s_123456/privacy_x9s_123456:16/PRIVATE/PRIVATE.12345678:user/release-keys");
        retired.put("future_value","KEEP");
        DeviceProfile old=new DeviceProfile(true,77,"oppo-x9s",retired,new LinkedHashSet<>(retired.keySet()),true,"110101","test",Set.of("latitude"),DeviceProfile.NETWORK_SIMULATE);
        DeviceProfile removed=DeviceProfile.parse(old.json());
        check(removed.enabled&&removed.preset.equals("custom")&&removed.revision==77,"Old OPPO profile becomes retained custom profile");
        for(String id:new String[]{"device","product","board","hardware","incremental","fingerprint"})
            check(!removed.values.containsKey(id)&&!removed.selected.contains(id),"Remove only known OPPO placeholder "+id);
        check(removed.values.get("imei").equals(old.values.get("imei"))&&removed.values.get("future_value").equals("KEEP"),"Retirement preserves IDs and unknown values");
        check(removed.locationEnabled&&removed.regionId.equals("110101")&&removed.networkMode.equals(DeviceProfile.NETWORK_SIMULATE),"Retirement preserves location and network choices");
        check(DeviceProfile.parse(removed.json()).json().equals(removed.json()),"Retirement is idempotent");
        for(int length:new int[]{92,128,256}){
            Map<String,String> longValues=new LinkedHashMap<>(x.values);
            longValues.put("fingerprint","T".repeat(length));
            DeviceProfile full=new DeviceProfile(true,88,"custom",longValues,x.selected);
            DeviceProfile parsed=DeviceProfile.parse(full.json());
            check(parsed.enabled&&parsed.revision==88,"Long fingerprint does not disable profile");
            check(parsed.get("fingerprint").equals(longValues.get("fingerprint")),"Full fingerprint survives parsing");
        }
        if(args.length>0){
            org.json.JSONObject captured=new org.json.JSONObject(java.nio.file.Files.readString(java.nio.file.Path.of(args[0]))).getJSONObject("properties");
            for(String key:captured.keySet()){
                String field=null;
                if(key.matches("ro\\.product\\.(?:(?:system_ext|system|vendor|product|odm)\\.)?(?:brand|manufacturer|model|device|name)"))
                    field=key.substring(key.lastIndexOf('.')+1).replace("name","product");
                else if(key.endsWith("build.fingerprint"))field="fingerprint";
                else if(key.endsWith("build.version.release"))field="release";
                else if(key.endsWith("build.version.incremental"))field="incremental";
                else if(key.equals("ro.product.board"))field="board";
                else if(key.equals("ro.hardware")||key.equals("ro.boot.hardware"))field="hardware";
                else if(key.equals("ro.sf.lcd_density"))field="density";
                if(field!=null)check(ModelPresets.property(v,key,field).equals(captured.getString(key)),"Match actual captured property "+key);
            }
        }
        System.out.println("PASS "+checks+" stock-preset, partition-property and legacy-migration assertions");
    }
}
