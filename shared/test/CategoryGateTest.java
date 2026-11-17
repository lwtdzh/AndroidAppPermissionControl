import io.github.lwtdzh.deviceprofile.*;
import org.json.JSONObject;
import java.util.*;

/** Every catalog field, all three gates, network modes, legacy documents and immutable updates. */
public final class CategoryGateTest {
    private static int checks;
    private static void check(boolean value,String message){checks++;if(!value)throw new AssertionError(message);}
    public static void main(String[] args)throws Exception {
        DeviceProfile base=DeviceProfile.preset("xiaomi-14");
        for(String group:List.of("ids","model","location","network","environment"))
            check(!base.groupEnabled(group)&&base.groupState(group,true).equals("已关闭"),"Default off "+group);
        Set<String> all=new LinkedHashSet<>(base.values.keySet());
        for(DeviceField field:DeviceField.ALL) {
            check(base.values.containsKey(field.id),"Fixture value "+field.id);
            for(boolean machine:new boolean[]{false,true})for(boolean category:new boolean[]{false,true})
                for(boolean child:new boolean[]{false,true}) {
                    Set<String> selected=new LinkedHashSet<>(all);if(!child)selected.remove(field.id);
                    DeviceProfile p=new DeviceProfile(machine,12,"custom",base.values,selected,
                        field.group.equals("location")&&category,"","",Set.of(),
                        field.group.equals("network")&&category?DeviceProfile.NETWORK_SIMULATE:DeviceProfile.NETWORK_OFF,
                        field.group.equals("model")&&category,field.group.equals("ids")&&category,
                        field.group.equals("environment")&&category);
                    check(Objects.equals(p.get(field.id),machine&&category&&child?base.values.get(field.id):null),
                        "Three gates "+field.id+" "+machine+" "+category+" "+child);
                    check(DeviceProfile.parse(p.json()).json().equals(p.json()),"Round-trip "+field.id);
                }
        }
        DeviceProfile enabled=new DeviceProfile(true,13,base.preset,base.values,all,true,"110101","test",Set.of("accuracy"),
            DeviceProfile.NETWORK_SIMULATE,true,true,true);
        check(enabled.with(false,14,enabled.values,enabled.selected,enabled.preset).get("imei")==null,"App master dominates");
        for(String group:List.of("ids","model","location","environment")){
            DeviceProfile off=enabled.withGroup(group,false);
            check(off.values.equals(enabled.values)&&off.selected.equals(enabled.selected),"Category off retains values "+group);
            for(DeviceField field:DeviceField.ALL){
                check(Objects.equals(off.get(field.id),field.group.equals(group)?null:enabled.get(field.id)),
                    "Only own category changes "+group+" "+field.id);
            }
            DeviceProfile saved=off.with(true,15,off.values,off.selected,off.preset);
            check(!saved.groupEnabled(group),"with() retains category "+group);
            check(saved.withGroup(group,true).get("imei")!=null,"Re-enable preserves other categories");
        }
        for(String mode:List.of("off","simulate","no_sim")){
            for(boolean machine:new boolean[]{false,true})for(DeviceField field:DeviceField.ALL){
                DeviceProfile p=new DeviceProfile(machine,20,"custom",base.values,all,false,"","",Set.of(),mode,false,true,false);
                boolean applies=machine&&(field.group.equals("ids")||field.group.equals("network")&&!mode.equals("off")&&
                    (!mode.equals("no_sim")||!DevicePackets.CELLULAR.contains(field.id)));
                check((p.get(field.id)!=null)==applies,"Network mode and IDs independence "+mode+" "+field.id);
            }
            DeviceProfile p=new DeviceProfile(true,21,"custom",base.values,Set.of(),false,"","",Set.of(),mode);
            for(String id:DevicePackets.CELLULAR)check(p.get(id)==null,"No forced cellular selection "+mode+" "+id);
            check(!p.groupState("network",true).isEmpty(),"All network states explicit");
        }
        JSONObject legacy=new JSONObject(enabled.json());legacy.remove("idsEnabled");legacy.remove("environmentEnabled");
        DeviceProfile migrated=DeviceProfile.parse(legacy.toString());
        check(!migrated.idsEnabled&&!migrated.environmentEnabled,"Missing category flags opt out");
        check(migrated.modelEnabled&&migrated.locationEnabled&&migrated.networkMode.equals("simulate"),"Keep existing explicit category choices");
        check(migrated.values.equals(enabled.values)&&migrated.selected.equals(enabled.selected),"Migration preserves draft data");
        legacy.remove("networkMode");
        check(DeviceProfile.parse(legacy.toString()).networkMode.equals("off"),"Missing network mode opts out");
        check(AttestationPrivacy.remove(0x900002c9,enabled)&&!AttestationPrivacy.remove(0x900002c9,enabled.withGroup("ids",false)),
            "Attestation identity requests use category gate");
        check(ModelPresets.property(enabled,"ro.build.tags","fingerprint")!=null&&
            ModelPresets.property(enabled.withGroup("model",false),"ro.build.tags","fingerprint")==null,"Native metadata uses category gate");
        check(ProfileWarnings.messages(enabled.withGroup("environment",false),"15",true).stream().noneMatch(v->v.contains("传感器")),
            "Inactive environment produces no sensor warning");
        Map<String,String> future=new LinkedHashMap<>(enabled.values);future.put("future_value","KEEP");
        Set<String> futureSelected=new LinkedHashSet<>(enabled.selected);futureSelected.add("future_value");
        DeviceProfile roundTrip=DeviceProfile.parse(enabled.with(true,30,future,futureSelected,"custom").json());
        check(roundTrip.values.get("future_value").equals("KEEP")&&roundTrip.selected.contains("future_value"),"Unknown field preserved");
        check(roundTrip.get("future_value")==null,"Unrecognized fields cannot bypass category metadata");
        System.out.println("PASS "+checks+" category, three-gate, network-mode and migration assertions");
    }
}
