package io.github.lwtdzh.developerstateshield;

import android.content.ContentResolver;
import android.content.ContentProviderClient;
import android.database.Cursor;
import android.net.Uri;
import android.os.Bundle;
import android.provider.Settings;
import android.util.Log;
import java.lang.reflect.Method;
import java.util.Arrays;
import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

public final class DeveloperModule implements IXposedHookLoadPackage {
    private static final String TAG = "DeveloperStateShield";
    private static boolean installed;
    private static final ThreadLocal<Integer> queryDepth = ThreadLocal.withInitial(() -> 0);
    static boolean hidden(String key) {
        return ("development_settings_enabled".equals(key)
            && io.github.lwtdzh.appstateshield.RuntimePolicy.enabled("developer"))
            || (("adb_enabled".equals(key) || "adb_wifi_enabled".equals(key))
            && io.github.lwtdzh.appstateshield.RuntimePolicy.enabled("debug"));
    }
    private static Class<?> optional(String name, ClassLoader loader) {
        return XposedHelpers.findClassIfExists(name, loader);
    }
    private static void hook(Class<?> type, String method, XC_MethodHook callback) {
        if (type == null) return;
        try { XposedBridge.hookAllMethods(type, method, callback); }
        catch (Throwable error) { Log.w(TAG, "hook unavailable: " + type.getName() + "." + method); }
    }
    static String property(String key, String original) {
        if (!io.github.lwtdzh.appstateshield.RuntimePolicy.enabled("debug")) return original;
        if ("init.svc.adbd".equals(key)) return "stopped";
        if ("init.svc_debug_pid.adbd".equals(key)) return "";
        if ("service.adb.tcp.port".equals(key) || "persist.adb.tcp.port".equals(key)) return "-1";
        if ("persist.service.adb.enable".equals(key) || "persist.sys.adb_enabled".equals(key)
            || "sys.usb.ffs.ready".equals(key)) return "0";
        if ("sys.usb.state".equals(key) || "sys.usb.config".equals(key)
            || "persist.sys.usb.config".equals(key)) {
            String kept = String.join(",", Arrays.stream(original.split(","))
                .filter(item -> !item.equals("adb") && !item.isEmpty()).toArray(String[]::new));
            return kept.isEmpty() ? "none" : kept;
        }
        return original;
    }
    private static boolean settings(Uri uri) {
        return uri != null && "settings".equals(uri.getAuthority());
    }
    private static final XC_MethodHook SETTING = new XC_MethodHook() {
        @Override protected void beforeHookedMethod(MethodHookParam p) {
            for (Object arg : p.args) if (arg instanceof String && hidden((String) arg)) {
                Class<?> result = ((Method) p.method).getReturnType();
                if (result == String.class) p.setResult("0");
                else if (result == int.class) p.setResult(0);
                else if (result == long.class) p.setResult(0L);
                else if (result == float.class) p.setResult(0f);
                return;
            }
        }
    };
    private static final XC_MethodHook CALL = new XC_MethodHook() {
        @Override protected void afterHookedMethod(MethodHookParam p) {
            if (p.hasThrowable() || !(p.getResult() instanceof Bundle)) return;
            boolean provider = false, get = false, selected = false;
            for (Object arg : p.args) {
                if (arg instanceof Uri && settings((Uri) arg)) provider = true;
                if ("settings".equals(arg)) provider = true;
                if (arg instanceof String && ((String) arg).startsWith("GET_")) get = true;
                if (arg instanceof String && hidden((String) arg)) selected = true;
            }
            // ContentProviderClient already carries the authority; avoid touching other providers.
            if (!provider && p.thisObject instanceof ContentProviderClient) {
                try {
                    Object authority = XposedHelpers.getObjectField(p.thisObject, "mAuthority");
                    provider = "settings".equals(authority);
                } catch (Throwable ignored) {}
            }
            if (provider && get && selected) {
                Bundle result = new Bundle((Bundle) p.getResult());
                result.putString("value", "0");
                p.setResult(result);
            }
        }
    };
    private static final XC_MethodHook QUERY = new XC_MethodHook() {
        @Override protected void beforeHookedMethod(MethodHookParam p) {
            Uri uri = null;
            int projection = -1;
            for (int i = 0; i < p.args.length; i++) {
                if (p.args[i] instanceof Uri) uri = (Uri) p.args[i];
            }
            if (!settings(uri)) return;
            int depth = queryDepth.get();
            queryDepth.set(depth + 1);
            p.setObjectExtra("query-depth", depth);
            if (depth > 0) return;
            Class<?>[] types = ((Method) p.method).getParameterTypes();
            for (int i = 0; i < types.length; i++)
                if (types[i] == String[].class) { projection = i; break; }
            String[] requested = projection < 0 ? null : (String[]) p.args[projection];
            p.setObjectExtra("settings-query", Boolean.TRUE);
            p.setObjectExtra("projection", requested);
            String selected = uri.getLastPathSegment();
            if (!hidden(selected)) {
                for (int i = 0; i < p.args.length; i++) {
                    Object arg = p.args[i];
                    String[] selectionArgs = arg instanceof Bundle
                        ? ((Bundle) arg).getStringArray(ContentResolver.QUERY_ARG_SQL_SELECTION_ARGS)
                        : arg instanceof String[] && i != projection ? (String[]) arg : null;
                    if (selectionArgs != null && selectionArgs.length == 1 && hidden(selectionArgs[0]))
                        selected = selectionArgs[0];
                }
            }
            p.setObjectExtra("selected-key", hidden(selected) ? selected : null);
            if (requested != null && !Arrays.asList(requested).contains("name")) {
                String[] extended = Arrays.copyOf(requested, requested.length + 1);
                extended[requested.length] = "name";
                p.args[projection] = extended;
            }
        }
        @Override protected void afterHookedMethod(MethodHookParam p) {
            Object depth = p.getObjectExtra("query-depth");
            if (depth != null) queryDepth.set((int) depth);
            if (!Boolean.TRUE.equals(p.getObjectExtra("settings-query")) || p.hasThrowable()
                || !(p.getResult() instanceof Cursor)) return;
            Cursor result = (Cursor) p.getResult();
            if (!(result instanceof SettingsCursor)) p.setResult(new SettingsCursor(result,
                (String[]) p.getObjectExtra("projection"), (String) p.getObjectExtra("selected-key")));
        }
    };
    @Override public synchronized void handleLoadPackage(XC_LoadPackage.LoadPackageParam load) {
        if (installed) return;
        installed = true;
        for (Class<?> type : new Class<?>[]{Settings.Global.class, Settings.Secure.class,
            Settings.System.class, optional("android.provider.Settings$NameValueCache", load.classLoader)})
            for (String method : new String[]{"getString", "getStringForUser", "getInt", "getIntForUser",
                "getLong", "getLongForUser", "getFloat", "getFloatForUser"}) hook(type, method, SETTING);
        for (Class<?> type : new Class<?>[]{ContentResolver.class, ContentProviderClient.class}) {
            hook(type, "call", CALL);
            hook(type, "query", QUERY);
        }
        Class<?> properties = optional("android.os.SystemProperties", load.classLoader);
        for (String method : new String[]{"get", "getInt", "getLong", "getBoolean"})
            hook(properties, method, new XC_MethodHook() {
                @Override protected void afterHookedMethod(MethodHookParam p) {
                    if (p.hasThrowable() || p.args.length == 0) return;
                    String key = (String) p.args[0];
                    String value = property(key, String.valueOf(p.getResult()));
                    if (value.equals(String.valueOf(p.getResult()))) return;
                    Class<?> result = ((Method) p.method).getReturnType();
                    if (result == String.class) p.setResult(value);
                    else if (result == int.class) p.setResult(parse(value, (int) p.args[1]));
                    else if (result == long.class) p.setResult((long) parse(value, 0));
                    else if (result == boolean.class) p.setResult(false);
                }
            });
        try {
            if (io.github.lwtdzh.appstateshield.RuntimePolicy.enabled("debug"))
                System.loadLibrary("developerstate");
        }
        catch (Throwable error) { Log.e(TAG, "native layer unavailable", error); }
        Log.i(TAG, "Java hooks installed");
    }
    private static int parse(String value, int fallback) {
        try { return Integer.parseInt(value); } catch (NumberFormatException ignored) { return fallback; }
    }
}
