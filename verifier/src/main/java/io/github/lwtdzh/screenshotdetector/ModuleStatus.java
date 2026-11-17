package io.github.lwtdzh.screenshotdetector;

import android.os.Bundle;
import org.json.*;
/** Replaced by the module in scoped processes. An absent hook is explicit. */
public final class ModuleStatus {
    public static Bundle snapshot() {
        Bundle value = new Bundle(); value.putBoolean("injected", false);
        value.putBoolean("policyLoaded", false);value.putBoolean("futureMethodEnabled", false);
        value.putBoolean("deviceEnabled", false);value.putLong("deviceRevision",0);
        value.putBoolean("locationEnabled",false);
        value.putBoolean("modelEnabled",false);value.putBoolean("idsEnabled",false);
        value.putBoolean("environmentEnabled",false);
        value.putString("networkMode","off");
        value.putStringArray("enabled", new String[0]); return value;
    }
    public static JSONObject json() {
        Bundle value=snapshot();JSONObject result=new JSONObject();
        try {
            for(String key:value.keySet()) {
                Object item=value.get(key);
                result.put(key,item instanceof String[]?new JSONArray((Object)item):item);
            }
            return result;
        }catch(JSONException error){throw new IllegalStateException(error);}
    }
}
