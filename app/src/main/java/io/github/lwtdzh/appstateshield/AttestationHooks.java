package io.github.lwtdzh.appstateshield;

import de.robv.android.xposed.*;
import io.github.lwtdzh.deviceprofile.AttestationPrivacy;
import io.github.lwtdzh.deviceprofile.DeviceProfile;
import java.lang.reflect.*;
import java.util.*;
import android.util.Log;

/** Filters typed request parameters before they leave the injected process. */
final class AttestationHooks {
    static volatile int removedCount;
    private static final Set<Method> installed = new HashSet<>();
    static void install(ClassLoader loader) {
        // Keystore2 facade and direct AIDL proxies: no response/certificate hooks.
        for(String name:new String[]{"android.security.KeyStoreSecurityLevel",
                "android.security.KeyStore",
                "android.system.keystore2.IKeystoreSecurityLevel$Stub$Proxy",
                "android.hardware.security.keymint.IKeyMintDevice$Stub$Proxy"})
            install(XposedHelpers.findClassIfExists(name,loader));
    }
    static synchronized void install(Class<?> type) {
        if(type==null)return;
        for(Method method:type.getDeclaredMethods()) {
            if(!method.getName().equals("generateKey") || !installed.add(method))continue;
            Class<?>[] parameters=method.getParameterTypes();
            for(int i=0;i<parameters.length;i++) {
                Class<?> parameter=parameters[i];
                boolean array=parameter.isArray() &&
                    parameter.getComponentType().getName().equals("android.hardware.security.keymint.KeyParameter");
                boolean collection=Collection.class.isAssignableFrom(parameter);
                boolean legacy=parameter.getName().equals("android.security.keymaster.KeymasterArguments");
                if(!array && !collection && !legacy)continue;
                final int index=i;
                try {
                    DeviceRuntime.countHook(1);
                    XposedBridge.hookMethod(method,new XC_MethodHook(){
                        @Override protected void beforeHookedMethod(MethodHookParam p)throws Throwable {
                            DeviceProfile profile=DeviceRuntime.snapshot();
                            if(!profile.enabled || p.args[index]==null)return;
                            Object source=p.args[index];
                            List<Object> kept=new ArrayList<>();
                            boolean old=source.getClass().getName().equals(
                                "android.security.keymaster.KeymasterArguments");
                            Iterable<?> entries=old ? (Collection<?>)XposedHelpers.getObjectField(source,"mArguments") :
                                source instanceof Collection ? (Collection<?>)source :
                                Arrays.asList((Object[])source);
                            boolean removed=false;
                            for(Object item:entries) {
                                // Read actual typed metadata; never guess by JSON keys or byte content.
                                if(item!=null && (old || item.getClass().getName().equals(
                                        "android.hardware.security.keymint.KeyParameter")) &&
                                        AttestationPrivacy.remove(XposedHelpers.getIntField(item,"tag"),profile)) {
                                    removed=true;removedCount++;continue;
                                }
                                kept.add(item);
                            }
                            if(!removed)return;
                            if(old) {
                                Object copy=XposedHelpers.newInstance(source.getClass());
                                @SuppressWarnings("unchecked")
                                Collection<Object> arguments=(Collection<Object>)XposedHelpers.getObjectField(copy,"mArguments");
                                arguments.addAll(kept);p.args[index]=copy;
                            }else if(source.getClass().isArray()) {
                                Object copy=Array.newInstance(source.getClass().getComponentType(),kept.size());
                                for(int n=0;n<kept.size();n++)Array.set(copy,n,kept.get(n));
                                p.args[index]=copy;
                            }else p.args[index]=kept;
                        }
                    });
                }catch(Throwable error){Log.w("DeviceProfile","Attestation request API unavailable");}
            }
        }
    }
}
