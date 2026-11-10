package io.github.lwtdzh.vpnstateshield;

import android.net.ConnectivityManager;
import android.net.LinkProperties;
import java.util.Properties;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;

/** Hide proxy observations while allowing the platform's socket/HTTP routing to read real metadata. */
public final class ProxyHooks {
    private static final java.util.List<String> KEYS = java.util.Arrays.asList(
        "http.proxyHost", "http.proxyPort", "https.proxyHost", "https.proxyPort",
        "socksProxyHost", "socksProxyPort", "http.proxySet", "https.proxySet", "proxyHost", "proxyPort");
    private static int logged;
    private static void hidden(String route) {
        if (logged++ < 8) android.util.Log.i("VpnStateShield", "proxy metadata hidden: " + route);
    }
    private static boolean proxyKey(Object key) {
        return key instanceof String && KEYS.contains(key);
    }
    private static boolean routing() {
        for (StackTraceElement frame : new Throwable().getStackTrace()) {
            String name = frame.getClassName(), method = frame.getMethodName();
            if (name.startsWith("io.github.lwtdzh.vpnstateshield.") || name.contains("Xposed")
                || name.contains("HookBridge")
                || name.startsWith("org.lsposed.") || name.equals("java.lang.System")
                || name.equals("java.lang.Thread") || name.startsWith("java.lang.reflect.")) continue;
            if (name.startsWith("WV.") || name.startsWith("org.chromium.")) return true;
            if (name.split("\\.").length < 3) continue;
            if (name.startsWith("sun.net.") || name.startsWith("libcore.net.")
                || name.startsWith("com.android.okhttp.") || name.startsWith("okhttp3.")
                || name.startsWith("org.apache.http.") || name.startsWith("java.net.")) return true;
            if (name.equals("java.util.Properties") || name.equals("java.util.Hashtable")) continue;
            if (name.equals("android.net.Proxy")) {
                if (method.startsWith("setHttpProxy") || method.equals("getProxy")) return true;
                continue;
            }
            if (name.equals("android.net.ConnectivityManager") || name.equals("android.net.LinkProperties")
                || name.startsWith("android.net.IConnectivityManager$")) continue;
            if (name.equals("android.app.ActivityThread")
                && (method.equals("handleSetCoreSettings") || method.equals("handleBindApplication")
                    || method.equals("updateHttpProxy"))) return true;
            // The first actual application caller is an observation, not a platform routing path.
            return false;
        }
        return false;
    }
    public static void install(ClassLoader loader) {
        Properties actual = System.getProperties();
        XposedBridge.hookAllMethods(System.class, "getProperty", new XC_MethodHook() {
            @Override protected void beforeHookedMethod(MethodHookParam p) {
                if (proxyKey(p.args[0]) && !routing()) {
                    hidden("System.getProperty");
                    p.setResult(p.args.length > 1 ? p.args[1] : null);
                }
            }
        });
        XC_MethodHook property = new XC_MethodHook() {
            @Override protected void beforeHookedMethod(MethodHookParam p) {
                if (p.thisObject == actual && proxyKey(p.args[0]) && !routing()) {
                    hidden("Properties");
                    p.setResult(p.args.length > 1 ? p.args[1] : null);
                }
            }
        };
        XposedBridge.hookAllMethods(Properties.class, "getProperty", property);
        XposedBridge.hookAllMethods(Properties.class, "get", property);
        XposedBridge.hookAllMethods(System.class, "getProperties", new XC_MethodHook() {
            @Override protected void afterHookedMethod(MethodHookParam p) {
                if (p.hasThrowable() || routing()) return;
                Properties view = new Properties();
                view.putAll((Properties) p.getResult());
                view.keySet().removeIf(ProxyHooks::proxyKey);
                p.setResult(view);
            }
        });
        XC_MethodHook metadata = new XC_MethodHook() {
            @Override protected void beforeHookedMethod(MethodHookParam p) {
                if (!routing()) { hidden("proxy info"); p.setResult(null); }
            }
        };
        for (String method : new String[]{"getDefaultProxy", "getProxyForNetwork"})
            XposedBridge.hookAllMethods(ConnectivityManager.class, method, metadata);
        Class<?> proxy = XposedHelpers.findClassIfExists("android.net.IConnectivityManager$Stub$Proxy", loader);
        if (proxy != null)
            for (String method : new String[]{"getDefaultProxy", "getProxyForNetwork"})
                XposedBridge.hookAllMethods(proxy, method, metadata);
        XposedBridge.hookAllMethods(LinkProperties.class, "getHttpProxy", metadata);
        for (String method : new String[]{"getDefaultHost", "getHost"})
            XposedBridge.hookAllMethods(android.net.Proxy.class, method, metadata);
        XC_MethodHook port = new XC_MethodHook() {
            @Override protected void beforeHookedMethod(MethodHookParam p) {
                if (!routing()) p.setResult(-1);
            }
        };
        for (String method : new String[]{"getDefaultPort", "getPort"})
            XposedBridge.hookAllMethods(android.net.Proxy.class, method, port);
    }
}
