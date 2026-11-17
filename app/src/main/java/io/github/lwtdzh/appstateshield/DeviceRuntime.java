package io.github.lwtdzh.appstateshield;

import android.app.Activity;
import android.app.Application;
import android.content.Context;
import android.database.ContentObserver;
import android.net.Uri;
import android.os.*;
import android.util.Log;
import io.github.lwtdzh.deviceprofile.DeviceProfile;
import io.github.lwtdzh.deviceprofile.ModelPresets;
import java.lang.reflect.Field;
import java.util.*;

/** One immutable snapshot per injected process. Getters never perform Binder IPC. */
public final class DeviceRuntime {
    private static volatile DeviceProfile profile = DeviceProfile.off();
    private static final Map<Field,Object> originals = new LinkedHashMap<>();
    private static boolean nativeLoaded;
    private static volatile boolean nativeReady;
    private static volatile int hookCount;
    private static ClassLoader targetLoader;
    private static boolean hooksInstalled;
    private static boolean moduleListInstalled;
    private static Handler worker;
    private static Context context;
    private static volatile int startedActivities;
    private static final Runnable poll=new Runnable(){
        @Override public void run(){reload();worker.postDelayed(this,2000);}
    };
    private static native void nativeUpdate(String[] keys, String[] values);
    private static native boolean nativeObjectsReady();
    private static native int[] nativeDiagnostics();

    public static DeviceProfile snapshot() { return profile; }
    public static String value(String id) { return profile.get(id); }
    public static String property(String key) {
        return ModelPresets.property(profile,key,DeviceHooks.properties().get(key));
    }
    public static int number(String id, int fallback) {
        String value=value(id); return value==null?fallback:Integer.parseInt(value);
    }
    public static double decimal(String id, double fallback) {
        String value=value(id); return value==null?fallback:Double.parseDouble(value);
    }
    static void countHook(int count) { hookCount+=count; }
    public static Bundle status() {
        Bundle b=new Bundle();
        b.putBoolean("deviceEnabled",profile.enabled);b.putLong("deviceRevision",profile.revision);
        b.putBoolean("idsEnabled",profile.idsEnabled);
        b.putBoolean("environmentEnabled",profile.environmentEnabled);
        b.putBoolean("modelEnabled",profile.modelEnabled);
        b.putBoolean("locationEnabled",profile.locationEnabled);
        b.putString("deviceRegion",profile.regionName);
        b.putString("networkMode",profile.networkMode);
        b.putInt("deviceHooks",hookCount);b.putBoolean("deviceNative",nativeReady);
        b.putBoolean("deviceNativeObjects",nativeReady && nativeObjectsReady());
        if(nativeReady) {
            int[] counters=nativeDiagnostics();
            b.putInt("deviceFileViews",counters[0]);b.putInt("deviceRemappedPages",counters[1]);
            b.putInt("deviceRetainedPages",counters[2]);b.putInt("deviceSyscallView",counters[3]);
            b.putInt("deviceSyscallErrno",counters[4]);
        }
        b.putInt("deviceAttestationIdsRemoved",AttestationHooks.removedCount);
        b.putStringArray("deviceSelected",profile.selected.toArray(new String[0]));
        return b;
    }
    static void start(Application application, Context target, ClassLoader loader, String initial) {
        context=target;
        targetLoader=loader;
        apply(DeviceProfile.parse(initial));
        HandlerThread thread=new HandlerThread("DeviceProfileWatch",android.os.Process.THREAD_PRIORITY_BACKGROUND);
        thread.start();worker=new Handler(thread.getLooper());
        try {
            context.getContentResolver().registerContentObserver(DeviceStore.uri(context.getPackageName()),false,
                new ContentObserver(worker) {
                    @Override public void onChange(boolean self) { reload(); }
                });
        } catch(Throwable error) { Log.w("DeviceProfile","Observer unavailable; polling active"); }
        application.registerActivityLifecycleCallbacks(new Application.ActivityLifecycleCallbacks(){
            @Override public void onActivityStarted(Activity activity){
                if(startedActivities++==0)worker.post(()->{worker.removeCallbacks(poll);worker.post(poll);});
            }
            @Override public void onActivityStopped(Activity activity){
                if(--startedActivities==0)worker.post(()->worker.removeCallbacks(poll));
            }
            @Override public void onActivityCreated(Activity activity,Bundle state){}
            @Override public void onActivityResumed(Activity activity){}
            @Override public void onActivityPaused(Activity activity){}
            @Override public void onActivitySaveInstanceState(Activity activity,Bundle state){}
            @Override public void onActivityDestroyed(Activity activity){}
        });
    }
    private static void reload() {
        try {
            Bundle b=context.getContentResolver().call(Uri.parse("content://"+PolicyProvider.AUTHORITY),
                "read",context.getPackageName(),null);
            if(b==null || !b.containsKey("device")) return;
            DeviceProfile next=DeviceProfile.parse(b.getString("device"));
            if(next.revision!=profile.revision || next.enabled!=profile.enabled) apply(next);
        } catch(Throwable ignored) {
            // Keep the last successfully read snapshot during temporary provider failures.
        }
    }
    private static synchronized void apply(DeviceProfile next) {
        if(next.enabled&&!hooksInstalled){
            DeviceHooks.install(targetLoader);
            hooksInstalled=true;
        }
        if ("true".equals(next.get("hide_module_apps")) && !moduleListInstalled) {
            ModuleListHooks.install(context);
            moduleListInstalled = true;
        }
        // A never-enabled process leaves device APIs and Build fields untouched.
        if(!hooksInstalled){profile=next;return;}
        for(Map.Entry<String,String> entry:DeviceHooks.buildFields().entrySet()) {
            try {
                String[] path=entry.getKey().split(":");
                Class<?> type=path.length==1?Build.class:Build.VERSION.class;
                Field field=type.getDeclaredField(path[path.length-1]);field.setAccessible(true);
                if(!originals.containsKey(field)) originals.put(field,field.get(null));
                String replacement=ModelPresets.build(next,entry.getKey(),entry.getValue());
                field.set(null,replacement==null?originals.get(field):replacement);
            } catch(Throwable error) { Log.w("DeviceProfile","Static field unavailable: "+entry.getKey()); }
        }
        if(next.enabled && !nativeLoaded) {
            nativeLoaded=true;
            try { NativeLibraries.load("devicestate");nativeReady=true; }
            catch(Throwable error) { Log.w("DeviceProfile","Native layer unavailable",error); }
        }
        if(nativeReady) {
            Map<String,String> pairs=new LinkedHashMap<>();
            for(Map.Entry<String,String> e:DeviceHooks.properties().entrySet()) {
                String v=ModelPresets.property(next,e.getKey(),e.getValue());if(v!=null) pairs.put(e.getKey(),v);
            }
            for(String key:new String[]{"wifi_mac","bt_mac"}) {
                String v=next.get(key);if(v!=null)pairs.put(key,v);
            }
            try { nativeUpdate(pairs.keySet().toArray(new String[0]),pairs.values().toArray(new String[0])); }
            catch(Throwable error) { nativeReady=false;Log.w("DeviceProfile","Native update unavailable",error); }
        }
        // Publish the revision only after the static fields and JNI snapshot are
        // ready. A reader observing this revision must not see the previous native values.
        profile=next;
    }
}
