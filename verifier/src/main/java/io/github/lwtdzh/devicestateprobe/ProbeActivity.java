package io.github.lwtdzh.devicestateprobe;

import android.app.Activity;
import android.content.ContentProviderClient;
import android.content.Intent;
import android.database.Cursor;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.NetworkInfo;
import android.net.NetworkRequest;
import android.net.Uri;
import android.net.VpnService;
import android.os.Bundle;
import android.os.Parcel;
import android.provider.Settings;
import android.widget.TextView;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.io.FileOutputStream;
import java.net.HttpURLConnection;
import java.net.NetworkInterface;
import java.net.URL;
import java.util.Collections;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public final class ProbeActivity extends Activity {
    static { System.loadLibrary("stateprobe"); }
    static native String nativeSnapshot();
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        TextView text = new TextView(this);
        text.setText("Device state probe");
        setContentView(text);
        String action = getIntent().getStringExtra("action");
        if ("vpn-start".equals(action)) {
            Intent consent = VpnService.prepare(this);
            if (consent != null) startActivityForResult(consent, 10);
            else startVpn();
        } else if ("vpn-stop".equals(action)) {
            startService(new Intent(this, ProbeVpnService.class).setAction("stop"));
        } else new Thread(() -> {
            JSONObject result = "selinux".equals(action) ? SelinuxProbe.snapshot(this) : snapshot();
            try (FileOutputStream out = new FileOutputStream(new File(getFilesDir(), "result.json"))) {
                out.write(result.toString(2).getBytes(java.nio.charset.StandardCharsets.UTF_8));
            } catch (Exception error) { android.util.Log.e("DeviceStateProbe", "write failed", error); }
            runOnUiThread(() -> text.setText(result.toString()));
        }, "state-probe").start();
    }
    private void startVpn() { startForegroundService(new Intent(this, ProbeVpnService.class)); }
    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == 10 && result == RESULT_OK) startVpn();
    }
    private interface Read { Object get() throws Exception; }
    private void read(JSONObject result, String key, Read reader) {
        try {
            Object value = reader.get();
            result.put(key, value == null ? JSONObject.NULL : value);
        }
        catch (Throwable error) {
            try { result.put(key, "ERROR:" + error.getClass().getSimpleName()); } catch (Exception ignored) {}
        }
    }
    private JSONObject snapshot() {
        JSONObject result = new JSONObject();
        read(result, "lifecycle", io.github.lwtdzh.screenshotdetector.LifecycleProbe::snapshot);
        Bundle marker = io.github.lwtdzh.screenshotdetector.ModuleStatus.snapshot();
        read(result, "module", () -> new JSONObject().put("injected", marker.getBoolean("injected"))
            .put("policyLoaded", marker.getBoolean("policyLoaded"))
            .put("enabled", new JSONArray(marker.getStringArray("enabled")))
            .put("futureMethodEnabled", marker.getBoolean("futureMethodEnabled")));
        read(result, "storedPolicy", () -> {
            Bundle policy = getContentResolver().call(Uri.parse("content://io.github.lwtdzh.appstateshield.policy"),
                "read", getPackageName(), null);
            return new JSONObject().put("disabled", new JSONArray(policy.getStringArray("disabled")))
                .put("custom", policy.getBoolean("custom"));
        });
        read(result, "foreignReadDenied", () -> {
            try {
                getContentResolver().call(Uri.parse("content://io.github.lwtdzh.appstateshield.policy"),
                    "read", "io.github.lwtdzh.appstateshield", null);
                return false;
            } catch (SecurityException expected) { return true; }
        });
        read(result, "writeDenied", () -> {
            try {
                getContentResolver().call(Uri.parse("content://io.github.lwtdzh.appstateshield.policy"),
                    "write", getPackageName(), null); return false;
            } catch (SecurityException expected) { return true; }
        });
        Uri policyUri = Uri.parse("content://io.github.lwtdzh.appstateshield.policy");
        for (String operation : new String[]{"otherPackage", "insert", "update", "delete", "query"}) {
            read(result, operation + "Denied", () -> {
                try {
                    switch (operation) {
                        case "otherPackage": getContentResolver().call(policyUri, "read",
                            getPackageName().endsWith(".samplea") ? "io.github.lwtdzh.screenshotdetector" :
                            "io.github.lwtdzh.screenshotdetector.samplea", null); break;
                        case "insert": getContentResolver().insert(policyUri, new android.content.ContentValues()); break;
                        case "update": getContentResolver().update(policyUri, new android.content.ContentValues(), null, null); break;
                        case "delete": getContentResolver().delete(policyUri, null, null); break;
                        case "query":
                            try (Cursor ignored = getContentResolver().query(policyUri, null, null, null, null)) {}
                            break;
                    }
                    return false;
                } catch (SecurityException expected) { return true; }
            });
        }
        for (String key : new String[]{"development_settings_enabled", "adb_enabled", "adb_wifi_enabled", "airplane_mode_on"}) {
            read(result, key + ".global", () -> Settings.Global.getInt(getContentResolver(), key, -7));
            read(result, key + ".secure", () -> Settings.Secure.getString(getContentResolver(), key));
            read(result, key + ".system", () -> Settings.System.getString(getContentResolver(), key));
            read(result, key + ".float", () -> Settings.Global.getFloat(getContentResolver(), key, -7));
            read(result, key + ".long", () -> Settings.Global.getLong(getContentResolver(), key, -7));
            read(result, key + ".call", () -> getContentResolver().call(
                Settings.Global.CONTENT_URI, "GET_global", key, null).getString("value"));
            read(result, key + ".clientCall", () -> {
                try (ContentProviderClient client = getContentResolver().acquireContentProviderClient("settings")) {
                    return client.call("GET_global", key, null).getString("value");
                }
            });
            read(result, key + ".query", () -> query(key, new String[]{"name", "value"}, false));
            read(result, key + ".valueOnly", () -> query(key, new String[]{"value"}, false));
            read(result, key + ".bundleQuery", () -> query(key, new String[]{"value"}, true));
        }
        read(result, "native", () -> new JSONObject(nativeSnapshot()));
        read(result, "selinux", () -> SelinuxProbe.snapshot(this));
        for (String key : new String[]{"init.svc.adbd", "sys.usb.config", "sys.usb.state",
            "service.adb.tcp.port", "ro.build.version.sdk"}) {
            read(result, key + ".java", () -> Class.forName("android.os.SystemProperties")
                .getMethod("get", String.class).invoke(null, key));
        }
        ConnectivityManager cm = getSystemService(ConnectivityManager.class);
        read(result, "vpnNetworks", () -> {
            int count = 0;
            for (Network network : cm.getAllNetworks()) {
                NetworkCapabilities caps = cm.getNetworkCapabilities(network);
                if (caps != null && caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN)) count++;
            }
            return count;
        });
        read(result, "activeVpn", () -> {
            NetworkCapabilities caps = cm.getNetworkCapabilities(cm.getActiveNetwork());
            return caps != null && caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN);
        });
        read(result, "activeNotVpn", () -> {
            NetworkCapabilities caps = cm.getNetworkCapabilities(cm.getActiveNetwork());
            return caps != null && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_VPN);
        });
        read(result, "legacyVpn", () -> cm.getNetworkInfo(ConnectivityManager.TYPE_VPN) != null
            && cm.getNetworkInfo(ConnectivityManager.TYPE_VPN).isConnected());
        read(result, "interfaces", () -> {
            JSONArray names = new JSONArray();
            for (NetworkInterface item : Collections.list(NetworkInterface.getNetworkInterfaces())) names.put(item.getName());
            return names;
        });
        read(result, "tunByName", () -> NetworkInterface.getByName("tun0") != null);
        read(result, "linkInterface", () -> {
            android.net.LinkProperties link = cm.getLinkProperties(cm.getActiveNetwork());
            return link == null ? JSONObject.NULL : link.getInterfaceName();
        });
        read(result, "linkTextTunnel", () -> cm.getLinkProperties(cm.getActiveNetwork()).toString().contains("tun0"));
        read(result, "activeInfoConnected", () -> cm.getActiveNetworkInfo() != null && cm.getActiveNetworkInfo().isConnected());
        read(result, "networks", () -> {
            JSONArray networks = new JSONArray();
            for (Network network : cm.getAllNetworks()) networks.put(network.toString());
            return networks;
        });
        read(result, "wifiTransport", () -> {
            for (Network network : cm.getAllNetworks()) {
                NetworkCapabilities caps = cm.getNetworkCapabilities(network);
                if (caps != null && caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) return true;
            }
            return false;
        });
        read(result, "parcelVpn", () -> {
            NetworkCapabilities caps = cm.getNetworkCapabilities(cm.getActiveNetwork());
            Parcel parcel = Parcel.obtain();
            try {
                caps.writeToParcel(parcel, 0);
                parcel.setDataPosition(0);
                return NetworkCapabilities.CREATOR.createFromParcel(parcel).hasTransport(NetworkCapabilities.TRANSPORT_VPN);
            } finally { parcel.recycle(); }
        });
        read(result, "callbackVpn", () -> {
            CountDownLatch received = new CountDownLatch(1);
            boolean[] vpn = {false};
            ConnectivityManager.NetworkCallback callback = new ConnectivityManager.NetworkCallback() {
                @Override public void onCapabilitiesChanged(Network network, NetworkCapabilities caps) {
                    vpn[0] |= caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN);
                    received.countDown();
                }
            };
            cm.registerDefaultNetworkCallback(callback);
            try {
                if (!received.await(8, TimeUnit.SECONDS)) throw new IllegalStateException("No real network callback");
                return vpn[0];
            } finally { cm.unregisterNetworkCallback(callback); }
        });
        read(result, "internet", () -> {
            HttpURLConnection connection = (HttpURLConnection) new URL("https://connectivitycheck.gstatic.com/generate_204").openConnection();
            connection.setConnectTimeout(10000);
            connection.setReadTimeout(10000);
            try { return connection.getResponseCode(); } finally { connection.disconnect(); }
        });
        read(result, "proxyFixture", ProbeActivity::proxyFixture);
        return result;
    }
    /** A real local HTTP proxy exchange plus deliberately constructed metadata observations. */
    static JSONObject proxyFixture() throws Exception {
        java.net.ServerSocket server = new java.net.ServerSocket(0, 1, java.net.InetAddress.getByName("127.0.0.1"));
        server.setSoTimeout(8000);
        java.net.ProxySelector selector = java.net.ProxySelector.getDefault();
        String host = System.setProperty("http.proxyHost", "127.0.0.1");
        String port = System.setProperty("http.proxyPort", Integer.toString(server.getLocalPort()));
        java.util.concurrent.atomic.AtomicBoolean proxied = new java.util.concurrent.atomic.AtomicBoolean();
        Thread listener = new Thread(() -> {
            try (java.net.Socket socket = server.accept()) {
                java.io.BufferedReader reader = new java.io.BufferedReader(new java.io.InputStreamReader(socket.getInputStream()));
                String request = reader.readLine();
                proxied.set(request != null && request.startsWith("GET http://state-probe.invalid/"));
                while (true) { String header = reader.readLine(); if (header == null || header.isEmpty()) break; }
                socket.getOutputStream().write("HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n".getBytes());
            } catch (Exception ignored) {}
        }, "local-proxy");
        listener.start();
        HttpURLConnection connection = null;
        try {
            JSONObject value = new JSONObject();
            value.put("hostVisible", System.getProperty("http.proxyHost") != null);
            value.put("portVisible", System.getProperty("http.proxyPort") != null);
            value.put("bulkHostVisible", System.getProperties().getProperty("http.proxyHost") != null);
            value.put("ordinaryProperty", System.getProperty("java.vm.name"));
            // Use the platform's process-local proxy configurator, as ActivityThread does.
            android.net.ProxyInfo config = android.net.ProxyInfo.buildDirectProxy("127.0.0.1", server.getLocalPort());
            for (java.lang.reflect.Method method : android.net.Proxy.class.getDeclaredMethods()) {
                if (method.getName().startsWith("setHttpProxy") && method.getParameterTypes().length == 1
                    && method.getParameterTypes()[0] == android.net.ProxyInfo.class) {
                    method.setAccessible(true);
                    method.invoke(null, config);
                    value.put("configurator", method.getName());
                    break;
                }
            }
            JSONArray routes = new JSONArray();
            for (java.net.Proxy route : java.net.ProxySelector.getDefault().select(new java.net.URI("http://state-probe.invalid/proxy-control")))
                routes.put(route.type().name());
            value.put("selectedProxyTypes", routes);
            connection = (HttpURLConnection) new URL("http://state-probe.invalid/proxy-control").openConnection();
            connection.setConnectTimeout(5000);
            connection.setReadTimeout(5000);
            try { value.put("response", connection.getResponseCode()); }
            catch (Exception error) { value.put("responseError", error.getClass().getSimpleName()); }
            listener.join(1000);
            value.put("actualHttpProxyUsed", proxied.get());
            return value;
        } finally {
            if (connection != null) connection.disconnect();
            server.close();
            if (host == null) System.clearProperty("http.proxyHost"); else System.setProperty("http.proxyHost", host);
            if (port == null) System.clearProperty("http.proxyPort"); else System.setProperty("http.proxyPort", port);
            java.net.ProxySelector.setDefault(selector);
        }
    }
    private JSONObject query(String key, String[] projection, boolean bundle) throws Exception {
        Cursor cursor;
        if (bundle) {
            Bundle args = new Bundle();
            args.putString(android.content.ContentResolver.QUERY_ARG_SQL_SELECTION, "name=?");
            args.putStringArray(android.content.ContentResolver.QUERY_ARG_SQL_SELECTION_ARGS, new String[]{key});
            cursor = getContentResolver().query(Settings.Global.CONTENT_URI, projection, args, null);
        } else cursor = getContentResolver().query(Settings.Global.CONTENT_URI, projection, "name=?", new String[]{key}, null);
        try (Cursor c = cursor) {
            if (c == null || !c.moveToFirst()) throw new IllegalStateException("No setting row");
            int value = c.getColumnIndexOrThrow("value");
            return new JSONObject().put("value", c.getString(value)).put("int", c.getInt(value))
                .put("long", c.getLong(value)).put("float", c.getFloat(value))
                .put("columns", new JSONArray(c.getColumnNames()));
        }
    }
}
