package io.github.lwtdzh.deviceprofile;

import org.json.*;
import java.util.*;

/** Immutable wire document; missing/corrupt data always starts opted out. */
public final class DeviceProfile {
    public static final String NETWORK_OFF="off", NETWORK_SIMULATE="simulate", NETWORK_NO_SIM="no_sim";
    public final String networkMode;
    public final boolean enabled;
    public final boolean modelEnabled;
    public final boolean locationEnabled;
    public final String regionId, regionName;
    public final Set<String> regionOverrides;
    public final long revision;
    public final String preset;
    public final Map<String,String> values;
    public final Set<String> selected;
    public DeviceProfile(boolean enabled,long revision,String preset,Map<String,String> values,Set<String> selected) {
        this(enabled,revision,preset,values,selected,false,"","",Collections.emptySet());
    }
    public DeviceProfile(boolean enabled,long revision,String preset,Map<String,String> values,Set<String> selected,
                         boolean locationEnabled,String regionId,String regionName,Set<String> regionOverrides) {
        this(enabled,revision,preset,values,selected,locationEnabled,regionId,regionName,regionOverrides,NETWORK_NO_SIM);
    }
    public DeviceProfile(boolean enabled,long revision,String preset,Map<String,String> values,Set<String> selected,
                         boolean locationEnabled,String regionId,String regionName,Set<String> regionOverrides,String networkMode) {
        this(enabled,revision,preset,values,selected,locationEnabled,regionId,regionName,regionOverrides,networkMode,false);
    }
    public DeviceProfile(boolean enabled,long revision,String preset,Map<String,String> values,Set<String> selected,
                         boolean locationEnabled,String regionId,String regionName,Set<String> regionOverrides,String networkMode,
                         boolean modelEnabled) {
        this.enabled=enabled;this.revision=revision;this.preset=preset;
        this.modelEnabled=modelEnabled;
        this.networkMode=validNetworkMode(networkMode)?networkMode:NETWORK_OFF;
        this.locationEnabled=locationEnabled;this.regionId=regionId;this.regionName=regionName;
        this.regionOverrides=Collections.unmodifiableSet(new LinkedHashSet<>(regionOverrides));
        this.values=Collections.unmodifiableMap(new LinkedHashMap<>(values));
        this.selected=Collections.unmodifiableSet(new LinkedHashSet<>(selected));
    }
    public static DeviceProfile off() { return new DeviceProfile(false,0,"custom",Collections.emptyMap(),Collections.emptySet()); }
    public String get(String id) {
        DeviceField field=DeviceField.find(id);
        if(!enabled)return null;
        // A simulated SIM is one cellular packet; never mix disabled real fields into it.
        if(!selected.contains(id)&&!(simulatedSim()&&DevicePackets.CELLULAR.contains(id)))return null;
        if(field!=null){
            if(field.group.equals("model")&&!modelEnabled)return null;
            if(field.group.equals("location")&&!locationEnabled)return null;
            if(field.group.equals("network") && (NETWORK_OFF.equals(networkMode) ||
                NETWORK_NO_SIM.equals(networkMode)&&DevicePackets.CELLULAR.contains(id)))return null;
        }
        return values.get(id);
    }
    public boolean noSim(){return enabled&&NETWORK_NO_SIM.equals(networkMode);}
    public boolean simulatedSim(){return enabled&&NETWORK_SIMULATE.equals(networkMode);}
    public static boolean validNetworkMode(String mode){
        return NETWORK_OFF.equals(mode)||NETWORK_SIMULATE.equals(mode)||NETWORK_NO_SIM.equals(mode);
    }
    public String json() {
        try {
            return new JSONObject().put("schema",1).put("enabled",enabled).put("revision",revision)
                .put("modelEnabled",modelEnabled)
                .put("preset",preset).put("values",new JSONObject(values)).put("selected",new JSONArray(selected))
                .put("locationEnabled",locationEnabled).put("regionId",regionId).put("regionName",regionName)
                .put("regionOverrides",new JSONArray(regionOverrides)).put("networkMode",networkMode).toString();
        } catch(JSONException e) { throw new IllegalStateException(e); }
    }
    public static DeviceProfile parse(String raw) {
        try {
            JSONObject j=new JSONObject(raw);
            if(j.optInt("schema")!=1) return off();
            Map<String,String> values=new LinkedHashMap<>(); Set<String> selected=new LinkedHashSet<>();
            JSONObject v=j.optJSONObject("values"); JSONArray a=j.optJSONArray("selected");
            if(v!=null) for(Iterator<String> keys=v.keys();keys.hasNext();) {
                String id=keys.next();DeviceField f=DeviceField.find(id);Object value=v.opt(id);
                if(value instanceof String && (f==null || f.validate((String)value)==null))
                    values.put(id,((String)value).trim());
            }
            if(a!=null) for(int i=0;i<a.length();i++) {
                String id=a.optString(i); if(values.containsKey(id)) selected.add(id);
            }
            // Reject inconsistent documents; UI writes are validated before committing.
            if(j.optBoolean("enabled") && (a==null || selected.size()!=a.length())) return off();
            if(j.optBoolean("enabled")&&NETWORK_SIMULATE.equals(j.optString("networkMode"))&&
                !values.keySet().containsAll(DevicePackets.CELLULAR))return off();
            Set<String> overrides=new LinkedHashSet<>();JSONArray o=j.optJSONArray("regionOverrides");
            if(o!=null)for(int i=0;i<o.length();i++)overrides.add(o.optString(i));
            String preset=j.optString("preset","custom");
            if(preset.equals("oppo-x9s")){ModelPresets.retireOppo(values,selected);preset="custom";}
            ModelPresets.migrateLegacy(preset,values,selected);
            return new DeviceProfile(j.optBoolean("enabled",false),j.optLong("revision"),preset,values,selected,
                j.optBoolean("locationEnabled",false),j.optString("regionId",""),j.optString("regionName",""),overrides,
                j.optString("networkMode",NETWORK_NO_SIM),j.optBoolean("modelEnabled",false));
        } catch(Exception e) { return off(); }
    }
    public DeviceProfile with(boolean on,long rev,Map<String,String> v,Set<String> s,String name) {
        return new DeviceProfile(on,rev,name,v,s,locationEnabled,regionId,regionName,regionOverrides,networkMode,modelEnabled);
    }
    public static DeviceProfile preset(String name) {
        Map<String,String> v=new LinkedHashMap<>();
        for(DeviceField f:DeviceField.ALL) if(f.random) v.put(f.id,f.generate());
        v.putAll(ModelPresets.values(name));
        v.putAll(DevicePackets.network());
        v.put("latitude","31.2304");v.put("longitude","121.4737");v.put("accuracy","30");
        v.put("timezone","Asia/Shanghai");v.put("language","zh-CN");v.put("hide_sensors","true");
        v.put("hide_module_apps","true");
        Set<String> selected=new LinkedHashSet<>();
        // Prepare the verified model fields, but the section master starts off.
        // Effective defaults are identifiers and no SIM; other sections opt in.
        for(DeviceField field:DeviceField.ALL)
            if((field.group.equals("ids")||field.group.equals("model"))&&v.containsKey(field.id))selected.add(field.id);
        selected.remove("drm_id");
        return new DeviceProfile(true,0,name,v,selected);
    }
}
