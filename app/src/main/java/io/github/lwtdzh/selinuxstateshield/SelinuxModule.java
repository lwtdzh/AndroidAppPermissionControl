package io.github.lwtdzh.selinuxstateshield;

import android.util.Log;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;

/** Observation only: never invokes setenforce or writes selinuxfs. */
public final class SelinuxModule {
    public static void install(ClassLoader loader) {
        Class<?> selinux = XposedHelpers.findClassIfExists("android.os.SELinux", loader);
        if (selinux != null) {
            XC_MethodHook enforcing = new XC_MethodHook() {
                @Override protected void beforeHookedMethod(MethodHookParam p) { p.setResult(true); }
            };
            XposedBridge.hookAllMethods(selinux, "isSELinuxEnabled", enforcing);
            XposedBridge.hookAllMethods(selinux, "isSELinuxEnforced", enforcing);
        }
        Class<?> properties = XposedHelpers.findClassIfExists("android.os.SystemProperties", loader);
        if (properties != null) XposedBridge.hookAllMethods(properties, "get", new XC_MethodHook() {
            @Override protected void afterHookedMethod(MethodHookParam p) throws Throwable {
                // Missing properties stay missing; boot metadata is not a runtime mode oracle.
                if (!p.hasThrowable() && "ro.boot.selinux".equals(p.args[0])
                    && p.getResult() instanceof String && !((String) p.getResult()).isEmpty()) {
                    Object raw = p.args.length == 1 ? p.getResult() :
                        XposedBridge.invokeOriginalMethod(p.method, null, new Object[]{p.args[0], ""});
                    if (!"".equals(raw)) p.setResult("enforcing");
                }
            }
        });
        try { System.loadLibrary("selinuxstate"); }
        catch (Throwable error) { Log.e("SELinuxStateShield", "native layer unavailable", error); }
    }
}
