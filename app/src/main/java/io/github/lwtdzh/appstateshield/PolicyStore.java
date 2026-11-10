package io.github.lwtdzh.appstateshield;

import android.content.Context;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.*;

/** One synchronous preference transaction stores the entire revision. */
public final class PolicyStore {
    private final android.content.SharedPreferences prefs;
    public PolicyStore(Context context) { prefs = context.getSharedPreferences("policies", Context.MODE_PRIVATE); }
    private JSONObject data() {
        try { return new JSONObject(prefs.getString("apps", "{}")); }
        catch (Exception error) { return new JSONObject(); }
    }
    public List<String> packages() {
        ArrayList<String> values = new ArrayList<>();
        data().keys().forEachRemaining(values::add);
        Collections.sort(values); return values;
    }
    public Set<String> disabled(String pkg) {
        LinkedHashSet<String> values = new LinkedHashSet<>();
        JSONArray array = data().optJSONArray(pkg);
        if (array != null) for (int i = 0; i < array.length(); i++) {
            Object item = array.opt(i);
            if (item instanceof String) values.add((String) item);
        }
        return values;
    }
    public synchronized boolean save(String pkg, Set<String> disabled) {
        JSONObject data = data();
        try { data.put(pkg, new JSONArray(new TreeSet<>(disabled))); }
        catch (Exception error) { return false; }
        return prefs.edit().putString("apps", data.toString()).commit();
    }
    public synchronized boolean remove(String pkg) {
        JSONObject data = data(); data.remove(pkg);
        return prefs.edit().putString("apps", data.toString()).commit();
    }
}
