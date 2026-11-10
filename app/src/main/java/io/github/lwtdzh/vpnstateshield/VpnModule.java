package io.github.lwtdzh.vpnstateshield;

import android.net.ConnectivityManager;
import android.net.LinkProperties;
import android.net.NetworkCapabilities;
import android.net.NetworkInfo;
import android.util.Log;
import java.net.NetworkInterface;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Enumeration;
import java.util.List;
import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

/** Vector owns application scope. Network handles and traffic routing are never replaced. */
public final class VpnModule implements IXposedHookLoadPackage {
    private static final String TAG = "VpnStateShield";
    private static boolean installed;
    private static boolean tunnel(String name) {
        return name != null && (name.matches("(tun|tap|ppp|ipsec|vti|wg)[0-9].*")
            || name.equals("utun") || name.matches("utun[0-9].*"));
    }
    private static Class<?> optional(String name, ClassLoader loader) {
        return XposedHelpers.findClassIfExists(name, loader);
    }
    private static void hook(Class<?> type, String method, XC_MethodHook callback) {
        if (type == null) return;
        try { XposedBridge.hookAllMethods(type, method, callback); }
        catch (Throwable error) { Log.w(TAG, "hook unavailable: " + type.getName() + "." + method); }
    }
    private static NetworkCapabilities sanitize(NetworkCapabilities caps) {
        if (caps == null) return null;
        // Inspect the actual bit field, avoiding recursion through our getter hooks.
        try {
            long transports = XposedHelpers.getLongField(caps, "mTransportTypes");
            XposedHelpers.setLongField(caps, "mTransportTypes",
                transports & ~(1L << NetworkCapabilities.TRANSPORT_VPN));
            long capabilities = XposedHelpers.getLongField(caps, "mNetworkCapabilities");
            XposedHelpers.setLongField(caps, "mNetworkCapabilities",
                capabilities | (1L << NetworkCapabilities.NET_CAPABILITY_NOT_VPN));
            Object info = XposedHelpers.getObjectField(caps, "mTransportInfo");
            if (info != null && info.getClass().getName().endsWith("VpnTransportInfo"))
                XposedHelpers.setObjectField(caps, "mTransportInfo", null);
        } catch (Throwable error) {
            Log.w(TAG, "capabilities layout unavailable: " + error.getClass().getSimpleName());
        }
        return caps;
    }
    private static final XC_MethodHook CAPS = new XC_MethodHook() {
        @Override protected void afterHookedMethod(MethodHookParam p) {
            if (!p.hasThrowable() && p.getResult() instanceof NetworkCapabilities)
                p.setResult(sanitize((NetworkCapabilities) p.getResult()));
        }
    };
    private static LinkProperties sanitizeLink(LinkProperties link) {
        if (link == null) return null;
        try {
            if (tunnel((String) XposedHelpers.getObjectField(link, "mIfaceName")))
                XposedHelpers.setObjectField(link, "mIfaceName", null);
            for (android.net.RouteInfo route : link.getRoutes()) {
                if (tunnel((String) XposedHelpers.getObjectField(route, "mInterface")))
                    XposedHelpers.setObjectField(route, "mInterface", null);
            }
            Object stacked = XposedHelpers.getObjectField(link, "mStackedLinks");
            if (stacked instanceof java.util.Map<?, ?>) {
                java.util.Map<?, ?> links = (java.util.Map<?, ?>) stacked;
                links.entrySet().removeIf(entry -> entry.getKey() instanceof String && tunnel((String) entry.getKey()));
                for (Object item : links.values())
                    if (item instanceof LinkProperties) sanitizeLink((LinkProperties) item);
            }
        } catch (Throwable error) {
            Log.w(TAG, "link properties layout unavailable: " + error.getClass().getSimpleName());
        }
        return link;
    }
    private static final XC_MethodHook LINK = new XC_MethodHook() {
        @Override protected void afterHookedMethod(MethodHookParam p) {
            if (!p.hasThrowable() && p.getResult() instanceof LinkProperties)
                p.setResult(sanitizeLink((LinkProperties) p.getResult()));
        }
    };
    private static final XC_MethodHook INFO = new XC_MethodHook() {
        @Override protected void afterHookedMethod(MethodHookParam p) {
            if (p.hasThrowable()) return;
            if (p.getResult() instanceof NetworkInfo) {
                NetworkInfo info = (NetworkInfo) p.getResult();
                if (info.getType() == ConnectivityManager.TYPE_VPN) p.setResult(null);
            } else if (p.getResult() instanceof NetworkInfo[]) {
                List<NetworkInfo> kept = new ArrayList<>();
                for (NetworkInfo info : (NetworkInfo[]) p.getResult())
                    if (info != null && info.getType() != ConnectivityManager.TYPE_VPN) kept.add(info);
                p.setResult(kept.toArray(new NetworkInfo[0]));
            }
        }
    };
    @Override public synchronized void handleLoadPackage(XC_LoadPackage.LoadPackageParam load) {
        if (installed) return;
        installed = true;
        // Service return values, including the generated Binder proxy used by direct callers.
        for (Class<?> type : new Class<?>[]{ConnectivityManager.class,
            optional("android.net.IConnectivityManager$Stub$Proxy", load.classLoader)}) {
            hook(type, "getNetworkCapabilities", CAPS);
            hook(type, "getLinkProperties", LINK);
            for (String method : new String[]{"getNetworkInfo", "getActiveNetworkInfo",
                "getAllNetworkInfo", "getActiveNetworkInfoForUid"}) hook(type, method, INFO);
        }
        // Parcelable construction also covers asynchronous callback deliveries and direct parcels.
        hook(NetworkCapabilities.CREATOR.getClass(), "createFromParcel", CAPS);
        hook(LinkProperties.CREATOR.getClass(), "createFromParcel", LINK);
        for (String method : new String[]{"toString", "writeToParcel"})
            hook(LinkProperties.class, method, new XC_MethodHook() {
                @Override protected void beforeHookedMethod(MethodHookParam p) {
                    sanitizeLink((LinkProperties) p.thisObject);
                }
            });
        XposedBridge.hookAllConstructors(NetworkCapabilities.class, new XC_MethodHook() {
            @Override protected void afterHookedMethod(MethodHookParam p) {
                sanitize((NetworkCapabilities) p.thisObject);
            }
        });
        hook(NetworkCapabilities.class, "hasTransport", new XC_MethodHook() {
            @Override protected void beforeHookedMethod(MethodHookParam p) {
                if ((int) p.args[0] == NetworkCapabilities.TRANSPORT_VPN) p.setResult(false);
            }
        });
        hook(NetworkCapabilities.class, "hasCapability", new XC_MethodHook() {
            @Override protected void beforeHookedMethod(MethodHookParam p) {
                if ((int) p.args[0] == NetworkCapabilities.NET_CAPABILITY_NOT_VPN) p.setResult(true);
            }
        });
        for (String method : new String[]{"getTransportTypes", "getCapabilities", "getTransportInfo",
            "toString", "writeToParcel"}) hook(NetworkCapabilities.class, method, new XC_MethodHook() {
                @Override protected void beforeHookedMethod(MethodHookParam p) {
                    sanitize((NetworkCapabilities) p.thisObject);
                }
            });
        XC_MethodHook interfaces = new XC_MethodHook() {
            @Override protected void afterHookedMethod(MethodHookParam p) {
                if (p.hasThrowable() || p.getResult() == null) return;
                List<NetworkInterface> kept = new ArrayList<>();
                Enumeration<?> all = (Enumeration<?>) p.getResult();
                while (all.hasMoreElements()) {
                    NetworkInterface item = (NetworkInterface) all.nextElement();
                    if (!tunnel(item.getName())) kept.add(item);
                }
                p.setResult(Collections.enumeration(kept));
            }
        };
        hook(NetworkInterface.class, "getNetworkInterfaces", interfaces);
        hook(NetworkInterface.class, "getSubInterfaces", interfaces);
        for (String method : new String[]{"getByName", "getByIndex", "getByInetAddress"})
            hook(NetworkInterface.class, method, new XC_MethodHook() {
                @Override protected void afterHookedMethod(MethodHookParam p) {
                    if (!p.hasThrowable() && p.getResult() instanceof NetworkInterface
                        && tunnel(((NetworkInterface) p.getResult()).getName())) p.setResult(null);
                }
            });
        hook(LinkProperties.class, "getInterfaceName", new XC_MethodHook() {
            @Override protected void afterHookedMethod(MethodHookParam p) {
                if (!p.hasThrowable() && tunnel((String) p.getResult())) p.setResult(null);
            }
        });
        hook(LinkProperties.class, "getAllInterfaceNames", new XC_MethodHook() {
            @Override protected void afterHookedMethod(MethodHookParam p) {
                if (p.hasThrowable() || !(p.getResult() instanceof List)) return;
                List<Object> kept = new ArrayList<>();
                for (Object name : (List<?>) p.getResult())
                    if (!(name instanceof String) || !tunnel((String) name)) kept.add(name);
                p.setResult(kept);
            }
        });
        try { System.loadLibrary("vpnstate"); }
        catch (Throwable error) { Log.e(TAG, "native layer unavailable", error); }
        Log.i(TAG, "Java hooks installed");
    }
}
