package io.github.lwtdzh.screenshotdetector;

import android.app.Application;
import android.content.*;
import android.database.Cursor;
import android.net.Uri;
import android.os.Bundle;
import android.provider.Settings;
import org.json.JSONObject;

/** Captures real early reads, including the Application and provider startup order. */
public final class LifecycleProbe extends Application {
    private static final JSONObject reads = new JSONObject();
    public static void capture(Context c, String stage) {
        try {
            Bundle marker = ModuleStatus.snapshot();
            reads.put(stage, new JSONObject().put("injected", marker.getBoolean("injected"))
                .put("developer", Settings.Global.getInt(c.getContentResolver(), "development_settings_enabled", -7))
                .put("debug", Settings.Global.getInt(c.getContentResolver(), "adb_enabled", -7))
                .put("selinux", io.github.lwtdzh.devicestateprobe.SelinuxProbe.enforced()));
        } catch (Exception e) {
            try { reads.put(stage, e.getClass().getSimpleName()); } catch (Exception ignored) {}
        }
    }
    @Override protected void attachBaseContext(Context base) {
        super.attachBaseContext(base); capture(base, "attachBaseContext");
    }
    @Override public void onCreate() { super.onCreate(); capture(this, "applicationOnCreate"); }
    public static JSONObject snapshot() { return reads; }
    public static final class Provider extends ContentProvider {
        @Override public boolean onCreate() { capture(getContext(), "providerOnCreate"); return true; }
        @Override public Cursor query(Uri u, String[] p, String s, String[] a, String o) { return null; }
        @Override public String getType(Uri u) { return null; }
        @Override public Uri insert(Uri u, ContentValues v) { return null; }
        @Override public int update(Uri u, ContentValues v, String s, String[] a) { return 0; }
        @Override public int delete(Uri u, String s, String[] a) { return 0; }
    }
}
