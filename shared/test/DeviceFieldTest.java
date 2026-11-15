import io.github.lwtdzh.deviceprofile.DeviceField;
import java.util.*;

/** Standalone JVM tests for formats and generated identifiers, without Android stubs. */
public final class DeviceFieldTest {
    private static int assertions;
    private static void check(boolean value,String message){
        if(!value)throw new AssertionError(message);assertions++;
    }
    public static void main(String[] args){
        Set<String> ids=new HashSet<>();
        for(DeviceField f:DeviceField.ALL){
            check(ids.add(f.id),"Duplicate field "+f.id);
            check(DeviceField.find(f.id)==f,"Catalog lookup "+f.id);
            if(f.random)for(int i=0;i<1000;i++){
                String value=f.generate();check(f.validate(value)==null,"Generated invalid "+f.id+": "+value);
                if(f.type.equals("imei"))check(DeviceField.luhn(value)==0 && value.startsWith("99"),"IMEI check digit");
                if(f.type.equals("mac")){
                    int first=Integer.parseInt(value.substring(0,2),16);
                    check((first&3)==2,"MAC must be local unicast");
                }
            }
        }
        String[][] bad={{"imei","123"},{"imei","123456789012345"},{"latitude","NaN"},
            {"longitude","181"},{"signal","-141"},{"pci","504"},{"width","319"},
            {"density","960.1"},{"timezone","Unknown/Zone"},{"android_id","x"},{"serial","abc"},
            {"oaid","123"},{"bt_mac","xx:00:00:00:00:00"},{"mcc","46"},{"mnc","0000"}};
        for(String[] pair:bad)check(DeviceField.find(pair[0]).validate(pair[1])!=null,"Accepted invalid "+Arrays.toString(pair));
        check(DeviceField.find("imei").validate("490154203237518")==null,"Known Luhn example");
        check(DeviceField.find("latitude").validate("-90")==null,"Latitude lower boundary");
        check(DeviceField.find("longitude").validate("180")==null,"Longitude upper boundary");
        check(DeviceField.find("phone").validate("")==null,"Blank phone is intentional");
        check(DeviceField.find("model").validate("X".repeat(92))!=null,"Legacy property buffer limit");
        for(int n:new int[]{91,92,128,256})
            check(DeviceField.find("fingerprint").validate("T".repeat(n))==null,"Full fingerprint byte boundary "+n);
        check(DeviceField.find("fingerprint").validate("T".repeat(257))!=null,"Fingerprint bound retained");
        check(DeviceField.find("fingerprint").validate("中".repeat(86))!=null,"Fingerprint UTF-8 byte bound");
        check(DeviceField.find("ssid").validate("中".repeat(11))!=null,"SSID byte length");
        System.out.println("PASS "+assertions+" device field assertions");
    }
}
