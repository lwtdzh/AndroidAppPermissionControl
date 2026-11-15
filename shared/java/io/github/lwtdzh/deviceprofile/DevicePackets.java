package io.github.lwtdzh.deviceprofile;

import java.security.SecureRandom;
import java.util.*;

/** One packet is created per refresh, then persisted; no random work in readers. */
public final class DevicePackets {
    public static final Set<String> CELLULAR=Set.of("imsi","iccid","phone","operator","mcc","mnc","lac","cid","tac","pci","signal");
    private static final SecureRandom RNG=new SecureRandom();
    private static String digits(int count){StringBuilder s=new StringBuilder();while(count-->0)s.append(RNG.nextInt(10));return s.toString();}
    public static Map<String,String> network(){
        String[][] carriers={{"中国移动","00","898600","138"},{"中国联通","01","898601","130"},{"中国电信","11","898603","133"}};
        String[] c=carriers[RNG.nextInt(carriers.length)];
        Map<String,String> packet=new LinkedHashMap<>();
        for(DeviceField f:DeviceField.ALL)if(f.group.equals("network")&&f.random)packet.put(f.id,f.generate());
        packet.put("operator",c[0]);packet.put("mcc","460");packet.put("mnc",c[1]);
        packet.put("imsi","460"+c[1]+digits(10));
        String card=c[2]+digits(12);packet.put("iccid",card+((10-DeviceField.luhn(card+"0"))%10));
        packet.put("phone",c[3]+digits(8));packet.put("signal",String.valueOf(-75-RNG.nextInt(25)));
        // All packet cellular fields use one operator; Wi-Fi/Bluetooth do not identify a carrier.
        return packet;
    }
    public static Map<String,String> group(String group,String preset){
        if(group.equals("network"))return network();
        Map<String,String> packet=new LinkedHashMap<>();
        DeviceProfile base=DeviceProfile.preset(preset);
        for(DeviceField f:DeviceField.ALL)if(f.group.equals(group)&&base.values.containsKey(f.id))
            packet.put(f.id,base.values.get(f.id));
        if(group.equals("ids")){
            String tac="99"+digits(6);
            for(String id:new String[]{"imei","imei2"}){
                String imei=tac+digits(6);packet.put(id,imei+((10-DeviceField.luhn(imei+"0"))%10));
            }
        }
        return packet;
    }
}
