package io.github.lwtdzh.appstateshield;

import android.content.Context;
import android.content.SharedPreferences;
import android.net.Uri;
import io.github.lwtdzh.deviceprofile.*;
import java.util.*;

/** Kept separate from the existing default-on blacklist. No exported write API. */
public final class DeviceStore {
    private final Context context;
    private final SharedPreferences prefs;
    public DeviceStore(Context c) { context=c; prefs=c.getSharedPreferences("device_profiles",Context.MODE_PRIVATE); }
    public DeviceProfile read(String pkg) { return DeviceProfile.parse(prefs.getString(pkg,"")); }
    public Set<String> packages() { return new TreeSet<>(prefs.getAll().keySet()); }
    public boolean save(String pkg,DeviceProfile p) {
        for(String id:p.selected) {
            DeviceField f=DeviceField.find(id);
            if(f==null ? !p.values.containsKey(id) : f.validate(p.values.get(id))!=null) return false;
        }
        long revision=Math.max(System.currentTimeMillis(),read(pkg).revision+1);
        boolean saved=prefs.edit().putString(pkg,p.with(p.enabled,revision,p.values,p.selected,p.preset).json()).commit();
        if(saved) { PolicyVisibility.grant(context,pkg); notifyTarget(pkg); }
        return saved;
    }
    public boolean remove(String pkg) {
        boolean saved=prefs.edit().remove(pkg).commit();
        if(saved) notifyTarget(pkg);
        return saved;
    }
    public static Uri uri(String pkg) { return Uri.parse("content://"+PolicyProvider.AUTHORITY+"/device/"+pkg); }
    private void notifyTarget(String pkg) { context.getContentResolver().notifyChange(uri(pkg),null); }
}
