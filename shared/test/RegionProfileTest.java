import io.github.lwtdzh.deviceprofile.*;
import java.io.*;
import java.util.*;

/** Gate truth table, legacy migration and every offline regional packet. */
public final class RegionProfileTest {
    private static int assertions;
    private static void check(boolean ok,String why){if(!ok)throw new AssertionError(why);assertions++;}
    public static void main(String[] args)throws Exception{
        ChinaRegions data=new ChinaRegions(new FileInputStream(args[0]));
        check(data.children("0").size()==34,"34 domestic province-level entries");
        int districts=0,missing=0;
        for(ChinaRegions.Region province:data.children("0"))for(ChinaRegions.Region city:data.children(province.id))
            for(ChinaRegions.Region district:data.children(city.id)){
                districts++;check(data.path(district).contains(city.name),"Parent path");
                if(!district.hasPoint()){missing++;continue;}
                Map<String,String> packet=data.packet(district);
                check(packet.size()==3,"Only coordinates and accuracy in location");
                check(packet.equals(data.packet(district)),"Stable repeated region selection");
                for(Map.Entry<String,String> entry:packet.entrySet()){
                    DeviceField f=DeviceField.find(entry.getKey());
                    check(f.group.equals("location")&&f.validate(entry.getValue())==null,"Valid regional "+entry.getKey());
                }
            }
        check(districts>2800&&missing>0,"Coverage including explicit missing points");
        DeviceProfile preset=DeviceProfile.preset("xiaomi-14");
        check(!preset.locationEnabled&&preset.get("latitude")==null&&preset.get("cid")==null,"Preset defaults location off");
        Map<String,String> values=new LinkedHashMap<>(preset.values);
        values.put("future_id","FUTURE_VALUE");Set<String> selected=new LinkedHashSet<>(values.keySet());
        for(boolean machine:new boolean[]{false,true})for(boolean location:new boolean[]{false,true})
            for(boolean field:new boolean[]{false,true}){
                Set<String> s=new LinkedHashSet<>(selected);if(!field)s.remove("latitude");
                DeviceProfile p=new DeviceProfile(machine,10,"custom",values,s,location,"110101","北京市 / 北京市 / 东城区",Set.of("latitude"));
                check((p.get("latitude")!=null)==(machine&&location&&field),"Three gates");
                check((p.get("imei")!=null)==machine,"Identifier independent of location");
                DeviceProfile parsed=DeviceProfile.parse(p.json());
                check(parsed.json().equals(p.json()),"Round-trip with unknown fields and metadata");
                check(parsed.with(machine,11,values,s,"custom").locationEnabled==location,"Save retains gate");
                check(parsed.values.equals(values),"Disable retains stored values");
            }
        String legacy=preset.json().replace("\"locationEnabled\":false,","");
        DeviceProfile migrated=DeviceProfile.parse(legacy);
        check(migrated.enabled&&!migrated.locationEnabled&&migrated.get("imei")!=null&&migrated.get("latitude")==null,"Legacy opts out of location");
        check(DeviceProfile.parse("{\"schema\":99}").get("latitude")==null,"Unknown schema off");
        for(String mode:new String[]{DeviceProfile.NETWORK_OFF,DeviceProfile.NETWORK_SIMULATE,DeviceProfile.NETWORK_NO_SIM})
            for(boolean on:new boolean[]{false,true}){
                DeviceProfile p=new DeviceProfile(on,0,preset.preset,values,selected,false,"","",Set.of(),mode);
                check(p.noSim()==(on&&mode.equals(DeviceProfile.NETWORK_NO_SIM)),"No SIM machine gate");
                check(p.simulatedSim()==(on&&mode.equals(DeviceProfile.NETWORK_SIMULATE)),"SIM machine gate");
                for(String id:DevicePackets.CELLULAR)
                    check((p.get(id)!=null)==(on&&mode.equals(DeviceProfile.NETWORK_SIMULATE)),"Cellular mode "+id);
                check((p.get("wifi_mac")!=null)==(on&&!mode.equals(DeviceProfile.NETWORK_OFF)),"Wi-Fi independent in no SIM");
                check(DeviceProfile.parse(p.json()).networkMode.equals(mode),"Mode round-trip");
            }
        DeviceProfile sparse=new DeviceProfile(true,0,"custom",values,Set.of(),false,"","",Set.of(),DeviceProfile.NETWORK_SIMULATE);
        check(sparse.get("imsi")!=null&&sparse.get("mnc")!=null&&sparse.get("wifi_mac")==null,"Cellular applies atomically");
        for(int n=0;n<30;n++){
            Map<String,String> network=DevicePackets.network();
            check(network.size()==15,"Whole network category");
            for(Map.Entry<String,String> e:network.entrySet())
                check(DeviceField.find(e.getKey()).validate(e.getValue())==null,"Valid network packet "+e.getKey());
            check(network.get("imsi").startsWith(network.get("mcc")+network.get("mnc")),"IMSI operator aligned");
            String[] carrier=network.get("mnc").equals("00")?new String[]{"中国移动","898600","138"}:
                network.get("mnc").equals("01")?new String[]{"中国联通","898601","130"}:new String[]{"中国电信","898603","133"};
            check(network.get("operator").equals(carrier[0])&&network.get("iccid").startsWith(carrier[1])&&
                network.get("phone").startsWith(carrier[2]),"Carrier packet aligned");
            check(DeviceField.luhn(network.get("iccid"))==0,"ICCID check digit");
        }
        for(String name:new String[]{"xiaomi-14","vivo-x200-pro-mini"}){
            Map<String,String> model=DevicePackets.group("model",name),ids=DevicePackets.group("ids",name);
            check(model.equals(DevicePackets.group("model",name)),"Model refresh restores fixed source data");
            if(model.containsKey("fingerprint"))check(
                model.get("fingerprint").contains("/"+model.get("product")+"/"+model.get("device")+":")&&
                model.get("fingerprint").contains(model.get("incremental")),"Matching model packet");
            check(ids.get("imei").substring(0,8).equals(ids.get("imei2").substring(0,8)),"Shared synthetic TAC");
            check(DeviceField.luhn(ids.get("imei"))==0&&DeviceField.luhn(ids.get("imei2"))==0,"Valid IMEIs");
        }
        System.out.println("PASS "+assertions+" region/profile assertions; "+districts+" districts, "+missing+" explicit missing points");
    }
}
