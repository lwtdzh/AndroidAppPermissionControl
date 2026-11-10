package io.github.lwtdzh.screenshotdetector;

import android.app.*;
import android.content.*;
import android.net.Uri;
import android.os.*;
import org.json.JSONObject;
import java.io.*;

/** ADB-only named fixtures and service counters; no payloads enter reports or logs. */
public final class FixtureActivity extends Activity {
    private boolean executed;
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        android.widget.TextView text = new android.widget.TextView(this);
        text.setText("Verification fixture"); setContentView(text);
    }
    private void execute() {
        String action = getIntent().getStringExtra("command");
        ClipboardManager clipboard = getSystemService(ClipboardManager.class);
        File saved = new File(getFilesDir(), "fixture-clipboard.bin");
        try {
            if ("clipboard-save".equals(action)) {
                Parcel parcel = Parcel.obtain();
                try {
                    ClipData original = clipboard.getPrimaryClip();
                    parcel.writeInt(original == null ? 0 : 1);
                    if (original != null) original.writeToParcel(parcel, 0);
                    try (FileOutputStream out = new FileOutputStream(saved)) { out.write(parcel.marshall()); }
                } finally { parcel.recycle(); }
            } else if ("clipboard-restore".equals(action)) {
                if (saved.exists()) {
                    byte[] bytes = java.nio.file.Files.readAllBytes(saved.toPath());
                    Parcel parcel = Parcel.obtain();
                    try {
                        parcel.unmarshall(bytes, 0, bytes.length); parcel.setDataPosition(0);
                        if (parcel.readInt() == 1) clipboard.setPrimaryClip(ClipData.CREATOR.createFromParcel(parcel));
                        else clipboard.clearPrimaryClip();
                    } finally { parcel.recycle(); saved.delete(); }
                }
            } else if ("clipboard-shot".equals(action)) {
                clipboard.setPrimaryClip(new ClipData("Screenshot fixture", new String[]{"image/png"},
                    new ClipData.Item(Uri.parse(getIntent().getStringExtra("uri")))));
            } else if ("clipboard-normal".equals(action)) {
                clipboard.setPrimaryClip(ClipData.newPlainText("ordinary fixture", "ordinary fixture"));
            } else if ("notification-normal".equals(action) || "notification-shot".equals(action)) {
                boolean shot = "notification-shot".equals(action);
                NotificationManager nm = getSystemService(NotificationManager.class);
                String channel = shot ? "screenshot-fixture" : "ordinary-fixture";
                nm.createNotificationChannel(new NotificationChannel(channel, "Verification fixture", NotificationManager.IMPORTANCE_LOW));
                nm.notify(shot ? 74103 : 74102, new Notification.Builder(this, channel)
                    .setSmallIcon(android.R.drawable.stat_notify_more)
                    .setContentTitle(shot ? "Screenshot verification fixture" : "ordinary fixture").build());
            } else if ("cancel-notification".equals(action)) {
                getSystemService(NotificationManager.class).cancel(74102);
                getSystemService(NotificationManager.class).cancel(74103);
            }
        } catch (Exception error) { throw new IllegalStateException("Fixture failed", error); }
    }
    @Override public void onWindowFocusChanged(boolean focused) {
        super.onWindowFocusChanged(focused);
        if (!focused) return;
        if (!executed) { executed = true; execute(); }
        try {
            ClipboardManager clipboard = getSystemService(ClipboardManager.class);
            JSONObject result = new JSONObject().put("notificationConnected", NotificationDetector.live != null)
                .put("accessibilityConnected", AccessibilityDetector.live != null)
                .put("notificationScreenshot", NotificationDetector.deliveredScreenshot)
                .put("notificationOrdinary", NotificationDetector.deliveredOrdinary)
                .put("accessibilityScreenshot", AccessibilityDetector.deliveredScreenshot)
                .put("accessibilityOrdinary", AccessibilityDetector.deliveredOrdinary)
                .put("clipboardVisible", clipboard.getPrimaryClip() != null)
                .put("clipboardHas", clipboard.hasPrimaryClip());
            try (FileOutputStream out = new FileOutputStream(new File(getFilesDir(), "services-result.json"))) {
                out.write(result.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));
            }
        } catch (Exception error) { throw new IllegalStateException("Fixture snapshot failed", error); }
    }
}
