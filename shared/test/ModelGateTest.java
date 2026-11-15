import io.github.lwtdzh.deviceprofile.*;
import java.util.*;
import org.json.*;

/** New model master/defaults only; no historical field or combination suites. */
public final class ModelGateTest {
    private static int checks;
    private static void check(boolean value,String name){if(!value)throw new AssertionError(name);checks++;}
    public static void main(String[] args)throws Exception {
        for(String preset:new String[]{"xiaomi-14","vivo-x200-pro-mini"}) {
            DeviceProfile defaults=DeviceProfile.preset(preset);
            check(!defaults.modelEnabled&&!defaults.locationEnabled&&defaults.noSim(),"Default masters");
            for(DeviceField field:DeviceField.ALL) {
                if(field.group.equals("model"))check(defaults.get(field.id)==null,"Model and screen off "+field.id);
                if(field.group.equals("network")||field.group.equals("environment")||field.group.equals("location"))
                    check(defaults.get(field.id)==null,"Only IDs and no SIM default "+field.id);
            }
            check(defaults.get("android_id")!=null&&defaults.get("imei")!=null,"Identifiers remain on");
            for(String id:new String[]{"width","height","density"})
                check(DeviceField.find(id).group.equals("model"),"Display joins model");
            JSONObject document=new JSONObject(defaults.json());document.remove("modelEnabled");
            DeviceProfile legacy=DeviceProfile.parse(document.toString());
            check(!legacy.modelEnabled&&legacy.values.equals(defaults.values)&&legacy.selected.equals(defaults.selected),
                "Existing profiles default off and retain values");
            document.put("modelEnabled",true);
            DeviceProfile on=DeviceProfile.parse(document.toString());
            for(DeviceField field:DeviceField.ALL)if(field.group.equals("model"))
                check(Objects.equals(on.get(field.id),on.values.get(field.id)),"Model master applies "+field.id);
            check(ModelPresets.property(on,"ro.build.id","fingerprint")!=null,"Fingerprint metadata opt in");
            check(ModelPresets.property(defaults,"ro.build.id","fingerprint")==null,"Metadata stays original when off");
            check(AttestationPrivacy.remove(0x900002cd,on)&&!AttestationPrivacy.remove(0x900002cd,defaults),
                "Attestation respects model master");
            check(AttestationPrivacy.remove(0x900002c9,defaults),"Identifier privacy independent");
            check(on.with(true,123,on.values,on.selected,on.preset).modelEnabled,"Save/update retains model flag");
            document.put("modelEnabled",false);
            DeviceProfile off=DeviceProfile.parse(document.toString());
            check(off.values.equals(on.values)&&off.selected.equals(on.selected),"Turning off retains all edits");
            document.put("modelEnabled",true).put("enabled",false);
            DeviceProfile masterOff=DeviceProfile.parse(document.toString());
            check(masterOff.get("width")==null&&masterOff.get("imei")==null,"Machine master dominates");
            check(ProfileWarnings.messages(defaults,"16",true).stream().noneMatch(s->s.contains("实际 API")),
                "Inactive model does not warn on release mismatch");
        }
        System.out.println("PASS "+checks+" new model master, merged display and default-selection assertions");
    }
}
