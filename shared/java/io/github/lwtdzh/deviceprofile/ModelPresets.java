package io.github.lwtdzh.deviceprofile;

import java.util.*;

/** Values backed by stock firmware or identified device observations. Never invent missing fields. */
public final class ModelPresets {
    private static final Map<String,String> XIAOMI, VIVO, XIAOMI_PROPERTIES, VIVO_PROPERTIES;
    static {
        Map<String,String> x=new LinkedHashMap<>();
        x.put("brand","Xiaomi");x.put("manufacturer","Xiaomi");x.put("model","23127PN0CG");
        x.put("device","houji");x.put("product","houji_global");x.put("board","houji");x.put("hardware","qcom");
        x.put("release","15");x.put("incremental","OS2.0.201.0.VNCMIXM");
        x.put("fingerprint","Xiaomi/houji_global/houji:15/AQ3A.240627.003/OS2.0.201.0.VNCMIXM:user/release-keys");
        x.put("width","1200");x.put("height","2670");x.put("density","480");
        x.put("total_ram","12");x.put("storage","256");
        XIAOMI=Collections.unmodifiableMap(x);
        Map<String,String> properties=new LinkedHashMap<>();
        String[][] partitions={
            {"system","Android","Xiaomi","mainline","generic","mainline"},
            {"system_ext","qti","QUALCOMM","qssi system image for arm64","missi","missi"},
            {"vendor","Xiaomi","Xiaomi","Xiaomi for arm64","mivendor","mivendor_sm8650_global"},
            {"odm","Xiaomi","Xiaomi","23127PN0CG","houji","houji_global"},
            {"product","Xiaomi","QUALCOMM","miproduct","miproduct","houji"}};
        String[] keys={"brand","manufacturer","model","device","name"};
        for(String[] partition:partitions)for(int i=0;i<keys.length;i++)
            properties.put("ro.product."+partition[0]+"."+keys[i],partition[i+1]);
        String incremental=x.get("incremental");
        properties.put("ro.vendor.build.fingerprint","Xiaomi/mivendor_sm8650_global/mivendor:14/UKQ1.240523.001/"+incremental+":user/release-keys");
        properties.put("ro.odm.build.fingerprint","Xiaomi/houji_global/houji:14/UKQ1.240523.001/"+incremental+":user/release-keys");
        properties.put("ro.product.build.fingerprint","Xiaomi/houji/miproduct:15/AQ3A.240627.003/"+incremental+":user/release-keys");
        properties.put("ro.system_ext.build.fingerprint","qti/missi/missi:15/AQ3A.240627.003/"+incremental+":user/release-keys");
        properties.put("ro.system.build.fingerprint",properties.get("ro.system_ext.build.fingerprint"));
        properties.put("ro.vendor.build.version.release","14");properties.put("ro.odm.build.version.release","14");
        XIAOMI_PROPERTIES=Collections.unmodifiableMap(properties);
        Map<String,String> v=new LinkedHashMap<>();
        v.put("brand","vivo");v.put("manufacturer","vivo");v.put("model","V2419A");
        v.put("device","PD2419");v.put("product","PD2419");v.put("board","k6991v1_64");
        v.put("hardware","mt6991");v.put("release","16");v.put("incremental","compiler261012170621");
        v.put("fingerprint","vivo/PD2419/PD2419:16/BP2A.250605.031.A3_V000L1/compiler261012170621:user/release-keys");
        v.put("width","1080");v.put("height","2344");v.put("density","480");
        VIVO=Collections.unmodifiableMap(v);
        Map<String,String> vivoProps=new LinkedHashMap<>();
        String[][] vivoPartitions={
            {"system","vivo","vivo","V2415A","PD2415","PD2415"},
            {"system_ext","vivo","vivo","vivo","mssi_64_64only_cn_armv82","sys_mssi_64_64only_cn_armv82"},
            {"vendor","vivo","vivo","V2415A","PD2415","PD2415"},
            {"product","vivo","vivo","vivo","mssi_64_64only_cn_armv82","sys_mssi_64_64only_cn_armv82"},
            {"odm","vivo","vivo","V2415A","PD2415","PD2415"}};
        for(String[] partition:vivoPartitions)for(int i=0;i<keys.length;i++)
            vivoProps.put("ro.product."+partition[0]+"."+keys[i],partition[i+1]);
        String systemFingerprint="vivo/PD2415/PD2415:16/BP2A.250605.031.A3/compiler261012170621:user/release-keys";
        String vendorFingerprint="vivo/PD2415/PD2415:15/AP3A.240905.015.A2/compiler261012170621:user/release-keys";
        for(String part:new String[]{"system","system_ext","product"}){
            vivoProps.put("ro."+part+".build.fingerprint",systemFingerprint);
            vivoProps.put("ro."+part+".build.version.release","16");
        }
        for(String part:new String[]{"vendor","odm"})vivoProps.put("ro."+part+".build.fingerprint",vendorFingerprint);
        vivoProps.put("ro.vendor.build.version.release","15");vivoProps.put("ro.odm.build.version.release","");
        vivoProps.put("ro.sf.lcd_density","560");
        VIVO_PROPERTIES=Collections.unmodifiableMap(vivoProps);
    }
    public static Map<String,String> values(String name){
        if("xiaomi-14".equals(name))return XIAOMI;
        if("vivo-x200-pro-mini".equals(name))return VIVO;
        return Collections.emptyMap();
    }
    public static List<String> missing(String name,String group){
        List<String> missing=new ArrayList<>();
        for(DeviceField f:DeviceField.ALL)if(f.group.equals(group)&&!values(name).containsKey(f.id))missing.add(f.id);
        return Collections.unmodifiableList(missing);
    }
    public static String version(String name){
        return "xiaomi-14".equals(name)?"HyperOS 2.0.201.0 · Android 15":
            "vivo-x200-pro-mini".equals(name)?"Android 16 · compiler261012170621":"";
    }
    /** Keep stock partition-specific identities when using the unchanged verified preset value. */
    public static String property(DeviceProfile profile,String key,String fieldId){
        if("fingerprint".equals(fieldId)){
            for(String suffix:new String[]{"id","type","tags"})if(key.endsWith(".build."+suffix)){
                String fingerprintKey=key.substring(0,key.length()-suffix.length())+"fingerprint";
                BuildFingerprint fingerprint=BuildFingerprint.parse(property(profile,fingerprintKey,"fingerprint"));
                return fingerprint==null?null:fingerprint.metadata(suffix.toUpperCase(Locale.ROOT));
            }
        }
        String value=profile.get(fieldId);
        if(value!=null&&"xiaomi-14".equals(profile.preset)&&value.equals(XIAOMI.get(fieldId)))
            return XIAOMI_PROPERTIES.getOrDefault(key,value);
        if(value!=null&&"vivo-x200-pro-mini".equals(profile.preset)&&value.equals(VIVO.get(fieldId)))
            return VIVO_PROPERTIES.getOrDefault(key,value);
        return value;
    }
    public static String build(DeviceProfile profile,String field,String fieldId){
        if(field.equals("ID")||field.equals("TYPE")||field.equals("TAGS")){
            BuildFingerprint fingerprint=BuildFingerprint.parse(profile.get("fingerprint"));
            return fingerprint==null?null:fingerprint.metadata(field);
        }
        return profile.get(fieldId);
    }
    /** Remove only our known old placeholders; retain custom values, flags and identifiers. */
    public static void migrateLegacy(String name,Map<String,String> values,Set<String> selected){
        Map<String,String> verified=values(name);if(verified.isEmpty())return;
        String oldCode="privacy_x14";
        String codePattern=oldCode+"(?:_\\d{6})?";
        boolean legacy=values.getOrDefault("device","").matches(codePattern)||
            values.getOrDefault("fingerprint","").matches("(?:OPPO|Xiaomi)/"+codePattern+"/"+codePattern+":16/PRIVATE/.+:user/release-keys");
        for(DeviceField f:DeviceField.ALL){
            String value=values.get(f.id);if(value==null)continue;
            boolean replace=(f.id.equals("device")||f.id.equals("product"))&&value.matches(codePattern)||
                f.id.equals("board")&&value.equals("privacy_board")||
                f.id.equals("hardware")&&value.equals("privacy_platform")||
                f.id.equals("incremental")&&value.matches("PRIVATE\\.\\d+")||
                f.id.equals("fingerprint")&&value.matches("(?:OPPO|Xiaomi)/"+codePattern+"/"+codePattern+":16/PRIVATE/.+:user/release-keys")||
                legacy&&f.id.equals("release")&&value.equals("16")||
                legacy&&f.id.equals("density")&&value.equals("420")||
                legacy&&f.id.equals("total_ram")&&value.equals("8");
            if(replace){
                if(verified.containsKey(f.id))values.put(f.id,verified.get(f.id));
                else {values.remove(f.id);selected.remove(f.id);}
            }
        }
        String ssid=values.get("ssid");
        if(ssid!=null&&ssid.matches("Private-[0-9a-f]{6}"))values.put("ssid","Home-"+ssid.substring(8));
    }
    public static void retireOppo(Map<String,String> values,Set<String> selected){
        for(DeviceField f:DeviceField.ALL)if(f.group.equals("model")){
            String value=values.get(f.id);
            if(value!=null&&(value.matches("privacy_x9s(?:_\\d{6})?")||value.equals("privacy_board")||
                value.equals("privacy_platform")||value.matches("PRIVATE\\.\\d+")||
                value.startsWith("OPPO/privacy_x9s"))){values.remove(f.id);selected.remove(f.id);}
        }
    }
    private ModelPresets(){}
}
