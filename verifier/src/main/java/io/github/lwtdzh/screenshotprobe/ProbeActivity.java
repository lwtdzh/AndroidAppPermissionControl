package io.github.lwtdzh.screenshotprobe;

import android.app.Activity;
import android.content.ContentProviderClient;
import android.content.ContentResolver;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.FileObserver;
import android.os.Handler;
import android.os.Looper;
import android.provider.MediaStore;
import android.util.Log;
import android.widget.TextView;
import java.io.File;
import java.io.FileInputStream;
import java.nio.file.Files;
import java.nio.file.Paths;
import org.json.JSONObject;

/** Deliberately uses multiple independent detection routes. Never part of the module APK. */
public final class ProbeActivity extends Activity {
    private static final String TAG = "ScreenshotProbe";
    private static final String ROOT = "/sdcard/Pictures/ShieldProbe/";
    private static final String SHOT = ROOT + "Screenshot_probe.png";
    private static final String PHOTO = ROOT + "ordinary_probe.png";
    private static final Uri IMAGES = MediaStore.Images.Media.EXTERNAL_CONTENT_URI;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final JSONObject result = new JSONObject();
    private TextView output;
    private int screenshotCallbacks, rawScreenshotCallbacks, mediaCallbacks, fileScreenshotEvents, fileNormalEvents;
    private android.os.IBinder activityTask;
    private android.os.Binder rawObserver;
    private android.os.IBinder activityToken;
    private int rawUnregister;
    private String documentKind;
    private int broadcastScreenshotEvents, broadcastNormalEvents;
    private FileObserver parent, shots;
    private android.database.ContentObserver observer;
    private ScreenCaptureCallback capture;
    private android.content.BroadcastReceiver receiver;
    private static native String nativeChecks(String directory, String screenshot, String ordinary, String cache);
    private static native void startWatch(String directory);
    private static native String drainWatch();
    private static native void stopWatch();
    static { System.loadLibrary("probe"); }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        output = new TextView(this);
        output.setPadding(32, 32, 32, 32);
        setContentView(output);
        try {
            getFilesDir().mkdirs();
            result.put("pid", android.os.Process.myPid());
            result.put("sdk", Build.VERSION.SDK_INT);
            if (Build.VERSION.SDK_INT >= 34) {
                capture = () -> { screenshotCallbacks++; render(); };
                registerScreenCaptureCallback(getMainExecutor(), capture);
                registerRaw();
            }
            observer = new android.database.ContentObserver(handler) {
                @Override public void onChange(boolean self, Uri changed) { mediaCallbacks++; render(); }
            };
            getContentResolver().registerContentObserver(IMAGES, true, observer);
            parent = watch(ROOT);
            shots = watch("/sdcard/Pictures/Screenshots/");
            parent.startWatching();
            shots.startWatching();
            startWatch(ROOT);
            receiver = new android.content.BroadcastReceiver() {
                @Override public void onReceive(android.content.Context context, android.content.Intent intent) {
                    if ("shieldprobe.SCREENSHOT".equals(intent.getAction())) broadcastScreenshotEvents++;
                    else broadcastNormalEvents++;
                }
            };
            android.content.IntentFilter filter = new android.content.IntentFilter("shieldprobe.SCREENSHOT");
            filter.addAction("shieldprobe.NORMAL");
            if (Build.VERSION.SDK_INT >= 33) registerReceiver(receiver, filter, RECEIVER_EXPORTED);
            else registerReceiver(receiver, filter);
            inspect();
        } catch (Throwable error) {
            put("startup_error", error.toString());
            render();
        }
    }
    private FileObserver watch(String path) {
        return new FileObserver(path, FileObserver.CREATE | FileObserver.CLOSE_WRITE | FileObserver.MOVED_TO) {
            @Override public void onEvent(int event, String name) {
                if (name == null) return;
                handler.post(() -> {
                    if (name.toLowerCase(java.util.Locale.ROOT).contains("screenshot")) fileScreenshotEvents++;
                    else fileNormalEvents++;
                    render();
                });
            }
        };
    }
    private int query(boolean bundle, boolean client, boolean idOnly) throws Exception {
        String[] columns = idOnly ? new String[]{"_id"} : new String[]{"_id", "_display_name", "relative_path"};
        String selection = "relative_path=?";
        String[] values = {"Pictures/ShieldProbe/"};
        Bundle options = new Bundle();
        options.putString(ContentResolver.QUERY_ARG_SQL_SELECTION, selection);
        options.putStringArray(ContentResolver.QUERY_ARG_SQL_SELECTION_ARGS, values);
        try (ContentProviderClient provider = client ? getContentResolver().acquireContentProviderClient(IMAGES) : null) {
            Cursor cursor = client ? provider.query(IMAGES, columns, options, null)
                : bundle ? getContentResolver().query(IMAGES, columns, options, null)
                : getContentResolver().query(IMAGES, columns, selection, values, "_id");
            try (Cursor owned = cursor) { return owned == null ? -1 : owned.getCount(); }
        }
    }
    private void inspect() {
        try {
            put("java_screenshot_exists", new File(SHOT).exists());
            put("java_normal_exists", new File(PHOTO).exists());
            put("java_list", new org.json.JSONArray(new File(ROOT).list()));
            put("java_screenshot_open", canRead(SHOT));
            put("java_normal_open", canRead(PHOTO));
            put("nio_screenshot_exists", Files.exists(Paths.get(SHOT)));
            put("nio_normal_exists", Files.exists(Paths.get(PHOTO)));
            put("media_legacy_count", query(false, false, false));
            put("media_bundle_count", query(true, false, false));
            put("media_client_count", query(true, true, false));
            put("media_id_only_count", query(false, false, true));
            put("native", new JSONObject(nativeChecks(ROOT, SHOT, PHOTO, getCacheDir().getAbsolutePath())));
            if (hasWindowFocus()) metadataChecks();
        } catch (Throwable error) { put("inspect_error", error.toString()); }
        render();
    }
    @Override public void onWindowFocusChanged(boolean focused) {
        super.onWindowFocusChanged(focused);
        if (focused) inspect();
    }
    private boolean canRead(String path) {
        try (FileInputStream stream = new FileInputStream(path)) { return stream.read() >= 0; }
        catch (Exception e) { return false; }
    }
    public static final class ProbeNotifications extends android.service.notification.NotificationListenerService {
        int screenshot, normal;
        @Override public void onNotificationPosted(android.service.notification.StatusBarNotification notification) {
            if (notification.getId() == 1) screenshot++;
            else normal++;
        }
    }
    public static final class ProbeAccessibility extends android.accessibilityservice.AccessibilityService {
        int screenshot, normal, packageControl;
        @Override public void onInterrupt() {}
        @Override public void onAccessibilityEvent(android.view.accessibility.AccessibilityEvent event) {
            if (event.getEventType() == android.view.accessibility.AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) screenshot++;
            else if (event.getEventType() == android.view.accessibility.AccessibilityEvent.TYPE_VIEW_CLICKED) normal++;
            else packageControl++;
        }
    }
    private void metadataChecks() {
        ProbeNotifications listener = new ProbeNotifications();
        for (boolean screenshot : new boolean[]{true, false}) {
            android.app.Notification notification = new android.app.Notification.Builder(this, screenshot ? "screenshots" : "general")
                .setContentTitle(screenshot ? "Screenshot saved" : "ordinary image").build();
            listener.onNotificationPosted(new android.service.notification.StatusBarNotification(
                "com.android.systemui", "com.android.systemui", screenshot ? 1 : 2, null,
                android.os.Process.myUid(), android.os.Process.myPid(), 0, notification, android.os.Process.myUserHandle(), 0));
        }
        put("notification_screenshot", listener.screenshot);
        put("notification_normal", listener.normal);
        ProbeAccessibility accessibility = new ProbeAccessibility();
        for (int i = 0; i < 3; i++) {
            android.view.accessibility.AccessibilityEvent event = android.view.accessibility.AccessibilityEvent.obtain(
                i == 0 ? android.view.accessibility.AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED
                : i == 1 ? android.view.accessibility.AccessibilityEvent.TYPE_VIEW_CLICKED
                : android.view.accessibility.AccessibilityEvent.TYPE_VIEW_FOCUSED);
            event.setPackageName(i == 2 ? getPackageName() : "com.android.systemui");
            event.setClassName(i == 0 ? "com.android.systemui.screenshot.ScreenshotView" : "android.widget.ImageView");
            accessibility.onAccessibilityEvent(event);
        }
        put("accessibility_screenshot", accessibility.screenshot);
        put("accessibility_normal", accessibility.normal);
        put("accessibility_package_name_control", accessibility.packageControl);
        android.content.ClipboardManager clipboard = getSystemService(android.content.ClipboardManager.class);
        android.content.ClipData old = clipboard.getPrimaryClip();
        try {
            clipboard.setPrimaryClip(new android.content.ClipData("Screenshot saved", new String[]{"image/png"},
                new android.content.ClipData.Item(Uri.parse("content://shieldprobe/fixture/1"))));
            put("clipboard_screenshot_visible", clipboard.getPrimaryClip() != null);
            put("clipboard_screenshot_description", clipboard.getPrimaryClipDescription() != null);
            put("clipboard_screenshot_has", clipboard.hasPrimaryClip());
            clipboard.setPrimaryClip(android.content.ClipData.newPlainText("ordinary", "ordinary text"));
            put("clipboard_normal_visible", clipboard.getPrimaryClip() != null && clipboard.hasPrimaryClip());
        } finally {
            if (old != null) clipboard.setPrimaryClip(old);
            else if (Build.VERSION.SDK_INT >= 28) clipboard.clearPrimaryClip();
        }
    }
    private void registerRaw() {
        try {
            activityTask = (android.os.IBinder) Class.forName("android.os.ServiceManager")
                .getDeclaredMethod("getService", String.class).invoke(null, "activity_task");
            java.lang.reflect.Method token = Activity.class.getDeclaredMethod("getActivityToken");
            token.setAccessible(true);
            activityToken = (android.os.IBinder) token.invoke(this);
            int rawRegister = getIntent().getIntExtra("raw_register", -1);
            rawUnregister = getIntent().getIntExtra("raw_unregister", -1);
            if (rawRegister < 0) {
                int[] codes = io.github.lwtdzh.screenshotdetector.FrameworkTransactions.capture();
                rawRegister = codes[0]; rawUnregister = codes[1];
            }
            put("raw_register_code", rawRegister);
            put("raw_unregister_code", rawUnregister);
            rawObserver = new android.os.Binder() {
                @Override protected boolean onTransact(int code, android.os.Parcel data, android.os.Parcel reply, int flags)
                    throws android.os.RemoteException {
                    if (code == FIRST_CALL_TRANSACTION) {
                        data.enforceInterface("android.app.IScreenCaptureObserver");
                        handler.post(() -> { rawScreenshotCallbacks++; render(); });
                        if (reply != null) reply.writeNoException();
                        return true;
                    }
                    return super.onTransact(code, data, reply, flags);
                }
            };
            rawTransact(rawRegister);
            put("raw_binder_registered", true);
        } catch (Throwable error) { put("raw_binder_error", error.toString()); }
    }
    private void rawTransact(int code) throws android.os.RemoteException {
        android.os.Parcel data = android.os.Parcel.obtain(), reply = android.os.Parcel.obtain();
        try {
            data.writeInterfaceToken("android.app.IActivityTaskManager");
            data.writeStrongBinder(activityToken);
            data.writeStrongBinder(rawObserver);
            if (!activityTask.transact(code, data, reply, 0)) throw new IllegalStateException("Binder transaction rejected");
            reply.readException();
        } finally { data.recycle(); reply.recycle(); }
    }
    private void put(String key, Object value) {
        try { result.put(key, value); } catch (Exception error) { throw new IllegalStateException(error); }
    }
    private void render() {
        put("screen_capture_callbacks", screenshotCallbacks);
        put("raw_screen_capture_callbacks", rawScreenshotCallbacks);
        put("media_callbacks", mediaCallbacks);
        put("file_screenshot_events", fileScreenshotEvents);
        put("file_normal_events", fileNormalEvents);
        put("broadcast_screenshot_events", broadcastScreenshotEvents);
        put("broadcast_normal_events", broadcastNormalEvents);
        put("manifest_screenshot_events", ManifestReceiver.screenshots);
        put("manifest_normal_events", ManifestReceiver.ordinary);
        output.setText(result.toString());
        try (java.io.FileOutputStream out = new java.io.FileOutputStream(new File(getFilesDir(), "screenshot-result.json"))) {
            out.write(result.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));
        } catch (Exception error) { Log.e(TAG, "Cannot save probe result", error); }
        Log.i(TAG, "RESULT " + result);
    }
    @Override protected void onNewIntent(android.content.Intent intent) {
        super.onNewIntent(intent);
        if ("pick_document".equals(intent.getStringExtra("command"))) {
            documentKind = intent.getStringExtra("doc_kind");
            android.content.Intent picker = new android.content.Intent(android.content.Intent.ACTION_OPEN_DOCUMENT);
            picker.addCategory(android.content.Intent.CATEGORY_OPENABLE);
            picker.setType("image/png");
            startActivityForResult(picker, 700);
        } else if ("document".equals(intent.getStringExtra("command"))) {
            documentCheck(intent);
        } else if ("drain".equals(intent.getStringExtra("command"))) {
            try { put("native_watch", new JSONObject(drainWatch())); }
            catch (Exception e) { put("watch_error", e.toString()); }
            inspect();
        } else if ("dispatch".equals(intent.getStringExtra("command"))) {
            // Explicit dispatch only tests listener routing, never claimed as a system screenshot.
            observer.dispatchChange(false, Uri.parse(intent.getStringExtra("uri")));
            handler.postDelayed(this::render, 200);
        } else inspect();
    }
    @Override protected void onActivityResult(int request, int resultCode, android.content.Intent data) {
        super.onActivityResult(request, resultCode, data);
        if (request == 700 && resultCode == RESULT_OK && data != null) {
            data.putExtra("doc_kind", documentKind);
            documentCheck(data);
        }
    }
    private void documentCheck(android.content.Intent intent) {
        String kind = intent.getStringExtra("doc_kind");
        Uri target = intent.getData();
        try (Cursor cursor = getContentResolver().query(target, new String[]{"document_id"}, null, null, null)) {
            put("document_" + kind + "_count", cursor == null ? -1 : cursor.getCount());
            put("document_" + kind + "_columns", cursor == null ? -1 : cursor.getColumnCount());
        } catch (Throwable error) { put("document_" + kind + "_error", error.toString()); }
        try (java.io.InputStream input = getContentResolver().openInputStream(target)) {
            put("document_" + kind + "_open", input != null && input.read() >= 0);
        } catch (Exception ignored) { put("document_" + kind + "_open", false); }
        render();
    }
    @Override public void onDestroy() {
        if (Build.VERSION.SDK_INT >= 34 && capture != null) unregisterScreenCaptureCallback(capture);
        if (rawObserver != null && activityTask != null) {
            try { rawTransact(rawUnregister); } catch (android.os.RemoteException ignored) {}
        }
        if (observer != null) getContentResolver().unregisterContentObserver(observer);
        if (parent != null) parent.stopWatching();
        if (shots != null) shots.stopWatching();
        if (receiver != null) unregisterReceiver(receiver);
        stopWatch();
        super.onDestroy();
    }
}
