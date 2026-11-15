package io.github.lwtdzh.appstateshield;

import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.os.Bundle;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** Filter typed PackageManager results for explicitly identified Xposed module APKs. */
final class ModuleListHooks {
    static void install(Context context) {
        PackageManager manager = context.getPackageManager();
        Set<String> modules = new HashSet<>();
        for (ApplicationInfo app : manager.getInstalledApplications(PackageManager.GET_META_DATA)) {
            Bundle metadata = app.metaData;
            if (metadata != null && Boolean.TRUE.equals(metadata.get("xposedmodule")) &&
                !app.packageName.equals(context.getPackageName()))
                modules.add(app.packageName);
        }
        Class<?> type = manager.getClass();
        XC_MethodHook list = new XC_MethodHook() {
            @Override protected void afterHookedMethod(MethodHookParam p) {
                if (!enabled() || p.hasThrowable() || !(p.getResult() instanceof List)) return;
                List<Object> kept = new ArrayList<>();
                for (Object item : (List<?>) p.getResult())
                    if (!modules.contains(packageName(item))) kept.add(item);
                p.setResult(kept);
            }
        };
        for (String method : new String[]{"getInstalledApplications", "getInstalledPackages",
                "getPackagesHoldingPermissions", "queryIntentActivities", "queryIntentServices",
                "queryBroadcastReceivers"})
            DeviceRuntime.countHook(XposedBridge.hookAllMethods(type, method, list).size());
        XC_MethodHook resolve = new XC_MethodHook() {
            @Override protected void afterHookedMethod(MethodHookParam p) {
                if (enabled() && !p.hasThrowable() && modules.contains(packageName(p.getResult())))
                    p.setResult(null);
            }
        };
        for (String method : new String[]{"resolveActivity", "resolveService"})
            DeviceRuntime.countHook(XposedBridge.hookAllMethods(type, method, resolve).size());
        XC_MethodHook direct = new XC_MethodHook() {
            @Override protected void beforeHookedMethod(MethodHookParam p) {
                if (enabled() && p.args.length > 0 && p.args[0] instanceof String &&
                    modules.contains((String) p.args[0]))
                    p.setThrowable(new PackageManager.NameNotFoundException((String) p.args[0]));
            }
        };
        for (String method : new String[]{"getApplicationInfo", "getPackageInfo"})
            DeviceRuntime.countHook(XposedBridge.hookAllMethods(type, method, direct).size());
    }
    private static boolean enabled() {
        return "true".equals(DeviceRuntime.value("hide_module_apps"));
    }
    private static String packageName(Object value) {
        if (value instanceof ApplicationInfo) return ((ApplicationInfo) value).packageName;
        if (value instanceof PackageInfo) return ((PackageInfo) value).packageName;
        if (value instanceof ResolveInfo) {
            ResolveInfo info = (ResolveInfo) value;
            if (info.activityInfo != null) return info.activityInfo.packageName;
            if (info.serviceInfo != null) return info.serviceInfo.packageName;
        }
        return null;
    }
}
