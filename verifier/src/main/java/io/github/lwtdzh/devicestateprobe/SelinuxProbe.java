package io.github.lwtdzh.devicestateprobe;

import android.content.Context;
import android.os.Bundle;
import android.provider.Settings;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;

public final class SelinuxProbe {
    static { System.loadLibrary("stateprobe"); }
    private static native String nativeSnapshot(String ordinary);
    private interface Read { Object get() throws Exception; }
    private static void read(JSONObject result, String key, Read action) {
        try { result.put(key, action.get()); }
        catch (Throwable error) {
            try { result.put(key, "ERROR:" + error.getClass().getSimpleName()); } catch (Exception ignored) {}
        }
    }
    public static boolean enforced() throws Exception {
        return (Boolean) Class.forName("android.os.SELinux").getMethod("isSELinuxEnforced").invoke(null);
    }
    public static JSONObject snapshot(Context context) {
        JSONObject result = new JSONObject();
        Bundle marker = io.github.lwtdzh.screenshotdetector.ModuleStatus.snapshot();
        read(result, "module", () -> new JSONObject().put("injected", marker.getBoolean("injected"))
            .put("policyLoaded", marker.getBoolean("policyLoaded"))
            .put("enabled", new JSONArray(marker.getStringArray("enabled")))
            .put("futureMethodEnabled", marker.getBoolean("futureMethodEnabled")));
        read(result, "lifecycle", io.github.lwtdzh.screenshotdetector.LifecycleProbe::snapshot);
        read(result, "javaEnforced", SelinuxProbe::enforced);
        read(result, "javaEnabled", () -> Class.forName("android.os.SELinux").getMethod("isSELinuxEnabled").invoke(null));
        File enforce = new File("/sys/fs/selinux/enforce");
        read(result, "fileInputStream", () -> {
            try (InputStream stream = new FileInputStream(enforce)) { return String.valueOf((char) stream.read()); }
        });
        read(result, "randomAccessFile", () -> {
            try (RandomAccessFile file = new RandomAccessFile(enforce, "r")) { return String.valueOf((char) file.read()); }
        });
        read(result, "nio", () -> new String(Files.readAllBytes(enforce.toPath()), java.nio.charset.StandardCharsets.UTF_8));
        read(result, "channel", () -> {
            try (FileChannel file = FileChannel.open(enforce.toPath())) {
                ByteBuffer buffer = ByteBuffer.allocate(1);
                if (file.read(buffer, 0) != 1) throw new IOException();
                return String.valueOf((char) buffer.get(0));
            }
        });
        read(result, "native", () -> {
            // An ordinary private file with the same basename must remain readable and unchanged.
            File ordinary = new File(context.getFilesDir(), "selinux-probe/enforce");
            if (!ordinary.getParentFile().isDirectory() && !ordinary.getParentFile().mkdirs()) throw new IOException();
            try (FileOutputStream out = new FileOutputStream(ordinary)) { out.write('0'); }
            try { return new JSONObject(nativeSnapshot(ordinary.getAbsolutePath())); }
            finally { ordinary.delete(); ordinary.getParentFile().delete(); }
        });
        read(result, "developer", () -> Settings.Global.getInt(context.getContentResolver(), "development_settings_enabled", -7));
        read(result, "debug", () -> Settings.Global.getInt(context.getContentResolver(), "adb_enabled", -7));
        read(result, "adbd", () -> Class.forName("android.os.SystemProperties").getMethod("get", String.class)
            .invoke(null, "init.svc.adbd"));
        read(result, "nativeState", () -> new JSONObject(ProbeActivity.nativeSnapshot()));
        read(result, "tunByName", () -> java.net.NetworkInterface.getByName("tun0") != null);
        read(result, "proxyFixture", ProbeActivity::proxyFixture);
        read(result, "screenshotFixture", () -> {
            try (InputStream stream = new FileInputStream("/sdcard/Pictures/SELinuxShieldProbe/Screenshot_control.txt")) {
                return stream.read() == '0';
            } catch (FileNotFoundException missing) { return false; }
        });
        read(result, "ordinaryFixture", () -> {
            try (InputStream stream = new FileInputStream("/sdcard/Pictures/SELinuxShieldProbe/ordinary_control.txt")) {
                return stream.read() == '0';
            }
        });
        read(result, "bootPropertyDefault", () -> Class.forName("android.os.SystemProperties").getMethod("get", String.class, String.class)
            .invoke(null, "ro.boot.selinux", "absent-control"));
        read(result, "bootProperty", () -> Class.forName("android.os.SystemProperties").getMethod("get", String.class)
            .invoke(null, "ro.boot.selinux"));
        return result;
    }
}
