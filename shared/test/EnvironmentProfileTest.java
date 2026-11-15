import io.github.lwtdzh.deviceprofile.*;
import java.util.*;

public final class EnvironmentProfileTest {
    private static int checks;
    private static void check(boolean ok,String message){if(!ok)throw new AssertionError(message);checks++;}
    public static void main(String[] args){
        for(String name:new String[]{"xiaomi-14","vivo-x200-pro-mini"}){
            DeviceProfile p=DeviceProfile.preset(name);
            BuildFingerprint f=BuildFingerprint.parse(p.get("fingerprint"));
            check(f!=null,"Stock format");
            check(ModelPresets.build(p,"ID","fingerprint").equals(f.id),"Root Build ID");
            check(ModelPresets.build(p,"TYPE","fingerprint").equals("user"),"Root type");
            check(ModelPresets.build(p,"TAGS","fingerprint").equals("release-keys"),"Root tags");
            for(String part:new String[]{"","system.","system_ext.","vendor.","product.","odm."}){
                String prefix="ro."+part+"build.";
                BuildFingerprint partition=BuildFingerprint.parse(ModelPresets.property(p,prefix+"fingerprint","fingerprint"));
                for(String suffix:new String[]{"id","type","tags"})
                    check(ModelPresets.property(p,prefix+suffix,"fingerprint").equals(
                        partition.metadata(suffix.toUpperCase(Locale.ROOT))),"Real partition metadata "+prefix+suffix);
            }
            Set<String> selected=new LinkedHashSet<>(p.selected);selected.remove("fingerprint");
            DeviceProfile deselected=p.with(true,2,p.values,selected,p.preset);
            DeviceProfile off=p.with(false,3,p.values,p.selected,p.preset);
            for(DeviceProfile disabled:new DeviceProfile[]{deselected,off}){
                check(ModelPresets.build(disabled,"ID","fingerprint")==null,"Build restored");
                check(ModelPresets.property(disabled,"ro.vendor.build.id","fingerprint")==null,"Native restored");
            }
            Map<String,String> custom=new LinkedHashMap<>(p.values);
            custom.put("fingerprint","Acme/P/D:16/CUSTOM.1/123:userdebug/test-keys");
            DeviceProfile manual=p.with(true,4,custom,p.selected,p.preset);
            check(ModelPresets.property(manual,"ro.vendor.build.id","fingerprint").equals("CUSTOM.1"),"Manual value derives, no stock guessing");
            check(ModelPresets.build(manual,"TAGS","fingerprint").equals("test-keys"),"Honor custom type/tags");
            check(!ProfileWarnings.messages(manual,"16",true).isEmpty(),"Mismatch warnings");
            custom.put("fingerprint","T".repeat(128));
            DeviceProfile incomplete=p.with(true,5,custom,p.selected,p.preset);
            check(incomplete.get("fingerprint").length()==128,"Opaque fingerprints retained");
            check(ModelPresets.build(incomplete,"ID","fingerprint")==null,"No invented metadata");
            check(ProfileWarnings.messages(incomplete,"16",true).get(0).contains("格式"),"Incomplete format warning");
            check(ProfileWarnings.messages(off,"16",true).isEmpty(),"No off warnings");
        }
        for(String bad:new String[]{"","X/P/D:16/I/N:user", "X/P/D:16/I/N:user/tags/extra",
            "X/P/D:16/I /N:user/tags","\nX/P/D:16/I/N:user/tags"})
            check(BuildFingerprint.parse(bad)==null,"Reject ambiguous format");
        DeviceProfile x=DeviceProfile.preset("xiaomi-14");
        List<String> warnings=ProfileWarnings.messages(x,"16",true);
        check(warnings.stream().anyMatch(w->w.contains("实际 API")),"Cross-release warning");
        check(warnings.stream().anyMatch(w->w.contains("一键登录")),"No-SIM carrier warning");
        check(warnings.stream().noneMatch(w->w.contains("不一致")),"Consistent stock profile");
        for(long originalTotal:new long[]{0,1,4096,8L<<30,4096L<<30}){
            for(long target:new long[]{0,1,1L<<30,4096L<<30}){
                long previous=-1;
                for(long original:new long[]{-1,0,1,4096,originalTotal/2,originalTotal,Long.MAX_VALUE}){
                    long remaining=CapacityView.remaining(original,originalTotal,target);
                    check(remaining>=0&&remaining<=target,"Bounded remaining");
                    if(original==originalTotal&&originalTotal>0)check(remaining==target,"Full ratio");
                    previous=remaining;
                }
            }
        }
        check(CapacityView.remaining(6L<<30,8L<<30,1L<<30)==3L*(1L<<28),"Preserve fraction");
        check(CapacityView.remaining(1,0,100)==0,"Unknown original not fabricated");
        check(CapacityView.total((8L<<30)+1,4096)*4096==(8L<<30),"Aligned blocks");
        System.out.println("PASS "+checks+" metadata, gates, warnings and capacity assertions");
    }
}
