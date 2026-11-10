package io.github.lwtdzh.devicestateprobe;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.Intent;
import android.net.VpnService;
import android.os.ParcelFileDescriptor;

/** Real TUN routed only to TEST-NET; ordinary Internet traffic continues over the original network. */
public final class ProbeVpnService extends VpnService {
    private ParcelFileDescriptor tun;
    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && "stop".equals(intent.getAction())) {
            // Android's VPN binding can keep a stopped service alive.
            // Release the interface now instead of waiting for onDestroy.
            releaseTun();
            stopForeground(STOP_FOREGROUND_REMOVE);
            stopSelf();
            return START_NOT_STICKY;
        }
        try {
            android.os.Bundle marker = io.github.lwtdzh.screenshotdetector.ModuleStatus.snapshot();
            org.json.JSONObject result = new org.json.JSONObject()
                .put("process", ":vpn").put("injected", marker.getBoolean("injected"))
                .put("policyLoaded", marker.getBoolean("policyLoaded"))
                .put("enabled", new org.json.JSONArray(marker.getStringArray("enabled")))
                .put("lifecycle", io.github.lwtdzh.screenshotdetector.LifecycleProbe.snapshot());
            try (java.io.FileOutputStream out = new java.io.FileOutputStream(new java.io.File(getFilesDir(), "vpn-result.json"))) {
                out.write(result.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));
            }
        } catch (Exception error) { android.util.Log.e("StateProbe", "VPN marker failed", error); }
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel("probe", "VPN probe", NotificationManager.IMPORTANCE_LOW));
        startForeground(1, new Notification.Builder(this, "probe")
            .setSmallIcon(android.R.drawable.stat_sys_warning).setContentTitle("VPN test fixture").build());
        if (tun == null) tun = new Builder().setSession("Device state probe")
            .addAddress("192.0.2.1", 32).addRoute("192.0.2.0", 24).establish();
        return START_NOT_STICKY;
    }
    private void releaseTun() {
        if (tun != null) try { tun.close(); } catch (Exception ignored) {}
        tun = null;
    }
    @Override public void onDestroy() {
        releaseTun();
        super.onDestroy();
    }
}
