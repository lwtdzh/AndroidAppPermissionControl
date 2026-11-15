package io.github.lwtdzh.screenshotdetector;

import android.content.Context;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.os.Bundle;
import org.json.JSONArray;
import org.json.JSONObject;

/** Actual PackageManager observations, independent of the stored privacy option. */
public final class ModuleListProbe {
    private static final String MODULE = "io.github.lwtdzh.appstateshield";
    public static int count(Context context) {
        int count = 0;
        for (ApplicationInfo app : context.getPackageManager().getInstalledApplications(PackageManager.GET_META_DATA))
            if (isModule(app)) count++;
        return count;
    }
    private static boolean isModule(ApplicationInfo app) {
        Bundle metadata = app == null ? null : app.metaData;
        return metadata != null && Boolean.TRUE.equals(metadata.get("xposedmodule"));
    }
    public static JSONObject read(Context context) {
        JSONObject result = new JSONObject();
        PackageManager pm = context.getPackageManager();
        try {
            JSONArray applications = new JSONArray(), packages = new JSONArray(), activities = new JSONArray();
            for (ApplicationInfo app : pm.getInstalledApplications(PackageManager.GET_META_DATA))
                if (isModule(app)) applications.put(app.packageName);
            for (PackageInfo pkg : pm.getInstalledPackages(PackageManager.GET_META_DATA))
                if (isModule(pkg.applicationInfo)) packages.put(pkg.packageName);
            Intent intent = new Intent(Intent.ACTION_MAIN).addCategory("de.robv.android.xposed.category.MODULE_SETTINGS");
            for (ResolveInfo info : pm.queryIntentActivities(intent, PackageManager.GET_META_DATA))
                activities.put(info.activityInfo.packageName);
            result.put("module", ModuleStatus.json()).put("pid", android.os.Process.myPid())
                .put("applications", applications).put("packages", packages).put("moduleActivities", activities);
            boolean appVisible = true, pkgVisible = true;
            try { pm.getApplicationInfo(MODULE, 0); }
            catch (PackageManager.NameNotFoundException e) { appVisible = false; }
            try { pm.getPackageInfo(MODULE, 0); }
            catch (PackageManager.NameNotFoundException e) { pkgVisible = false; }
            result.put("directApplicationVisible", appVisible).put("directPackageVisible", pkgVisible)
                .put("selfVisible", pm.getPackageInfo(context.getPackageName(), 0) != null)
                .put("ordinarySettingsVisible", pm.getApplicationInfo("com.android.settings", 0) != null);
        } catch (Exception error) {
            try { result.put("error", error.getClass().getSimpleName()); } catch (Exception ignored) {}
        }
        return result;
    }
}
