package io.github.lwtdzh.appstateshield;

import android.app.Application;
import android.content.Context;
import android.net.Uri;
import android.os.Bundle;
import android.util.Log;
import de.robv.android.xposed.*;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

public final class IntegratedEntry implements IXposedHookLoadPackage {
    private static boolean installed;
    @Override public void handleLoadPackage(XC_LoadPackage.LoadPackageParam load) {
        if ("io.github.lwtdzh.appstateshield".equals(load.packageName)) return;
        XposedHelpers.findAndHookMethod(Application.class, "attach", Context.class, new XC_MethodHook() {
            @Override protected void beforeHookedMethod(MethodHookParam p) {
                synchronized (IntegratedEntry.class) {
                    if (installed) return; installed = true;
                }
                Context context = (Context) p.args[0];
                String[] disabled = null;
                boolean loaded = false;
                try {
                    Bundle policy = context.getContentResolver().call(Uri.parse("content://" + PolicyProvider.AUTHORITY),
                        "read", context.getPackageName(), null);
                    if (policy == null || !policy.containsKey("disabled")) throw new IllegalStateException();
                    disabled = policy.getStringArray("disabled"); loaded = true;
                } catch (Throwable error) {
                    Log.w("AppStateShield", "Policy unavailable; using all enabled: " + error.getClass().getSimpleName());
                }
                RuntimePolicy.set(disabled);
                if (RuntimePolicy.enabled("screenshot")) install(() ->
                    new io.github.lwtdzh.screenshotshield.ShieldModule().handleLoadPackage(load));
                if (RuntimePolicy.enabled("vpn")) install(() ->
                    new io.github.lwtdzh.vpnstateshield.VpnModule().handleLoadPackage(load));
                if (RuntimePolicy.enabled("proxy")) install(() ->
                    io.github.lwtdzh.vpnstateshield.ProxyHooks.install(load.classLoader));
                if (RuntimePolicy.enabled("developer") || RuntimePolicy.enabled("debug")) install(() ->
                    new io.github.lwtdzh.developerstateshield.DeveloperModule().handleLoadPackage(load));
                if (RuntimePolicy.enabled("selinux")) install(() ->
                    io.github.lwtdzh.selinuxstateshield.SelinuxModule.install(load.classLoader));
                final boolean fromProvider = loaded;
                // The verifier reports injection separately from system observations.
                Class<?> status = XposedHelpers.findClassIfExists(
                    "io.github.lwtdzh.screenshotdetector.ModuleStatus", load.classLoader);
                if (status != null) XposedBridge.hookAllMethods(status, "snapshot", new XC_MethodHook() {
                    @Override protected void beforeHookedMethod(MethodHookParam h) {
                        Bundle marker = new Bundle();
                        marker.putBoolean("injected", true);
                        marker.putBoolean("policyLoaded", fromProvider);
                        marker.putStringArray("enabled", RuntimePolicy.enabledIds());
                        marker.putBoolean("futureMethodEnabled", RuntimePolicy.enabled("future-test-method"));
                        h.setResult(marker);
                    }
                });
                Log.i("AppStateShield", "Policy loaded=" + loaded + " enabled="
                    + java.util.Arrays.toString(RuntimePolicy.enabledIds()));
            }
        });
    }
    private static void install(Runnable installer) {
        try { installer.run(); }
        catch (Throwable error) { Log.e("AppStateShield", "Hook installation failed", error); }
    }
}
