package io.github.lwtdzh.screenshotdetector;

import android.content.Context;
import android.net.*;
import android.provider.Settings;
import java.io.FileInputStream;
import java.util.LinkedHashMap;
import java.util.Map;

/** Read-only, ordinary observations; never runs the diagnostic fixtures. */
final class ObservedState {
    private interface Read { int get() throws Exception; }
    private static void read(Map<String, Integer> values, String key, Read action) {
        try { values.put(key, action.get()); }
        catch (Exception | LinkageError e) { values.put(key, R.string.summary_unknown); }
    }
    private static int toggle(int value) {
        return value == 1 ? R.string.summary_on : value == 0 ? R.string.summary_off : R.string.summary_unknown;
    }
    static Map<String, Integer> read(Context context) {
        Map<String, Integer> values = new LinkedHashMap<>();
        ConnectivityManager cm = context.getSystemService(ConnectivityManager.class);
        read(values, "vpn", () -> {
            for (Network network : cm.getAllNetworks()) {
                NetworkCapabilities caps = cm.getNetworkCapabilities(network);
                if (caps != null && caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN)) return R.string.summary_on;
            }
            return R.string.summary_off;
        });
        read(values, "proxy", () -> {
            ProxyInfo proxy = cm.getDefaultProxy();
            boolean configured = proxy != null && ((proxy.getHost() != null && !proxy.getHost().isEmpty())
                || (proxy.getPacFileUrl() != null && !android.net.Uri.EMPTY.equals(proxy.getPacFileUrl())));
            return configured ? R.string.summary_configured : R.string.summary_not_configured;
        });
        read(values, "developer", () -> toggle(Settings.Global.getInt(context.getContentResolver(),
            "development_settings_enabled", -1)));
        read(values, "usb", () -> toggle(Settings.Global.getInt(context.getContentResolver(), "adb_enabled", -1)));
        read(values, "wireless", () -> toggle(Settings.Global.getInt(context.getContentResolver(), "adb_wifi_enabled", -1)));
        read(values, "selinux", () -> {
            // The Java boolean can collapse security_getenforce() == -1 to false.
            // Prefer an actual byte; false alone cannot prove Permissive.
            try (FileInputStream input = new FileInputStream("/sys/fs/selinux/enforce")) {
                int value = input.read();
                if (value == '1') return R.string.summary_enforcing;
                if (value == '0') return R.string.summary_permissive;
            } catch (java.io.IOException | SecurityException ignored) {}
            try {
                Class<?> api = Class.forName("android.os.SELinux");
                if (!(Boolean) api.getMethod("isSELinuxEnabled").invoke(null)) return R.string.summary_off;
                return (Boolean) api.getMethod("isSELinuxEnforced").invoke(null)
                    ? R.string.summary_enforcing : R.string.summary_selinux_unconfirmed;
            } catch (ReflectiveOperationException | SecurityException e) {
                return R.string.summary_unknown;
            }
        });
        return values;
    }
}
