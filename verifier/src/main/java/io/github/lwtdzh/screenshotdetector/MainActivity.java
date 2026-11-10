package io.github.lwtdzh.screenshotdetector;

import android.Manifest;
import android.app.Activity;
import android.content.*;
import android.database.Cursor;
import android.graphics.Insets;
import android.net.Uri;
import android.os.*;
import android.provider.*;
import android.util.Log;
import android.util.Size;
import android.view.*;
import android.widget.*;
import java.text.DateFormat;
import java.util.*;
import java.util.concurrent.Executors;
import java.util.concurrent.ExecutorService;

/** Foreground UI, receiving only real registrations, reads, and service deliveries. */
public final class MainActivity extends Activity implements Signals.Listener {
    private static final int PHOTOS = 10, DOCUMENT = 11;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final ArrayList<String> lines = new ArrayList<>();
    private final EnumMap<Source, TextView> states = new EnumMap<>(Source.class);
    private final EnumMap<Source, LinkedHashSet<String>> seen = new EnumMap<>(Source.class);
    private final EnumMap<Source, Long> recent = new EnumMap<>(Source.class);
    private TextView count, log;
    private Spinner choices;
    private EditText broadcast;
    private Detector detector;
    private int detections;
    private boolean foreground;
    private Source selected;
    private int generation;
    private boolean destroyed;
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        if (Build.VERSION.SDK_INT < 34) {
            startActivity(new Intent(this, io.github.lwtdzh.devicestateprobe.ProbeActivity.class));
            finish(); return;
        }
        detector = new Detector(this);
        if (saved != null) {
            detections = saved.getInt("count");
            ArrayList<String> old = saved.getStringArrayList("lines");
            if (old != null) lines.addAll(old);
            int source = saved.getInt("source", -1);
            if (source >= 0 && source < Source.values().length) selected = Source.values()[source];
        }
        LinearLayout root = column();
        root.setBackgroundColor(0xfffafafa);
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            Insets b = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
            view.setPadding(dp(16) + b.left, dp(8) + b.top, dp(16) + b.right, dp(8) + b.bottom);
            return insets;
        });
        root.addView(text(getString(R.string.app_name), 24));
        Bundle marker = ModuleStatus.snapshot();
        root.addView(text("Vector: " + marker.getBoolean("injected") + " · "
            + Arrays.toString(marker.getStringArray("enabled")), 13));
        LinearLayout probes = new LinearLayout(this);
        Button device = new Button(this); device.setText(R.string.device_probe); device.setContentDescription("device-probe");
        device.setOnClickListener(v -> startActivity(new Intent(this, io.github.lwtdzh.devicestateprobe.ProbeActivity.class)));
        probes.addView(device, new LinearLayout.LayoutParams(0, -2, 1));
        Button low = new Button(this); low.setText(R.string.screenshot_probe); low.setContentDescription("screenshot-probe");
        low.setOnClickListener(v -> startActivity(new Intent(this, io.github.lwtdzh.screenshotprobe.ProbeActivity.class)));
        probes.addView(low, new LinearLayout.LayoutParams(0, -2, 1)); root.addView(probes);
        count = text("", 18); root.addView(count);
        LinearLayout controls = column();
        controls.addView(text(getString(R.string.intro), 13));
        choices = new Spinner(this);
        choices.setContentDescription("source-filter");
        ArrayList<String> labels = new ArrayList<>();
        labels.add(getString(R.string.all_sources));
        for (Source s : Source.values()) labels.add(getString(s.label(this)));
        ArrayAdapter<String> adapter = new ArrayAdapter<>(this, android.R.layout.simple_spinner_item, labels);
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        choices.setAdapter(adapter);
        choices.setSelection(selected == null ? 0 : selected.ordinal() + 1);
        controls.addView(choices);
        controls.addView(text(getString(R.string.permissions_notice), 12));
        LinearLayout grants = new LinearLayout(this);
        addButton(grants, R.string.grant_photos, () -> requestPermissions(
            new String[]{Manifest.permission.READ_MEDIA_IMAGES,
                Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED}, PHOTOS));
        addButton(grants, R.string.grant_files, () -> settings(new Intent(
            Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION, Uri.parse("package:" + getPackageName()))));
        controls.addView(grants);
        LinearLayout services = new LinearLayout(this);
        addButton(services, R.string.grant_notifications, () -> settings(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)));
        addButton(services, R.string.grant_accessibility, () -> settings(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)));
        controls.addView(services);
        broadcast = new EditText(this);
        broadcast.setSingleLine();
        broadcast.setContentDescription("broadcast-action");
        broadcast.setHint(R.string.broadcast_hint);
        broadcast.setText(getPreferences(MODE_PRIVATE).getString("action", ""));
        controls.addView(broadcast);
        LinearLayout actions = new LinearLayout(this);
        addButton(actions, R.string.restart, this::restart);
        addButton(actions, R.string.check_document, () -> {
            Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("image/*")
                .addCategory(Intent.CATEGORY_OPENABLE)
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            startActivityForResult(intent, DOCUMENT);
        });
        controls.addView(actions);
        controls.addView(text(getString(R.string.manual_notice), 12));
        controls.addView(text(getString(R.string.test_instructions), 12));
        for (Source s : Source.values()) {
            TextView row = text(getString(s.label(this)) + " · " + getString(R.string.state_preparing), 12);
            states.put(s, row); seen.put(s, new LinkedHashSet<>());
            controls.addView(row);
        }
        ScrollView controlsScroll = new ScrollView(this);
        controlsScroll.addView(controls);
        root.addView(controlsScroll, new LinearLayout.LayoutParams(-1, 0, 1.2f));
        LinearLayout tools = new LinearLayout(this);
        addButton(tools, R.string.clear_log, () -> { lines.clear(); detections = 0; render(); });
        root.addView(tools);
        log = text("", 14); log.setTextIsSelectable(true);
        log.setBackgroundColor(0xffffffff); log.setPadding(dp(10), dp(10), dp(10), dp(10));
        ScrollView logs = new ScrollView(this); logs.addView(log);
        root.addView(logs, new LinearLayout.LayoutParams(-1, 0, 1f));
        setContentView(root);
        choices.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override public void onItemSelected(AdapterView<?> parent, View view, int position, long id) {
                selected = position == 0 ? null : Source.values()[position - 1];
                restart();
            }
            @Override public void onNothingSelected(AdapterView<?> parent) { }
        });
        render();
    }
    private LinearLayout column() {
        LinearLayout value = new LinearLayout(this); value.setOrientation(LinearLayout.VERTICAL); return value;
    }
    private int dp(int n) { return Math.round(n * getResources().getDisplayMetrics().density); }
    private TextView text(String text, int size) {
        TextView value = new TextView(this);
        value.setText(text); value.setTextSize(size); value.setPadding(0, dp(3), 0, dp(3)); return value;
    }
    private void addButton(LinearLayout parent, int label, Runnable action) {
        Button button = new Button(this); button.setText(label); button.setTextSize(12);
        button.setContentDescription(getResources().getResourceEntryName(label));
        button.setOnClickListener(view -> action.run());
        parent.addView(button, new LinearLayout.LayoutParams(0, -2, 1));
    }
    private void settings(Intent intent) {
        try { startActivity(intent); }
        catch (ActivityNotFoundException e) { Toast.makeText(this, R.string.state_unsupported, Toast.LENGTH_LONG).show(); }
    }
    private void restart() {
        if (!foreground) return;
        generation++;
        for (Set<String> ids : seen.values()) ids.clear();
        recent.clear();
        String action = broadcast.getText().toString().trim();
        getPreferences(MODE_PRIVATE).edit().putString("action", action).apply();
        detector.start(selected, action);
    }
    @Override protected void onStart() {
        super.onStart(); if (detector == null) return;
        // FileObserver shares one inotify thread. Stop the old page before
        // adding watches for the same directories on the new page.
        Signals.Listener previous = Signals.listener;
        if (previous instanceof MainActivity && previous != this)
            ((MainActivity) previous).stopListening();
        foreground = true; Signals.listener = this;
        main.post(this::restart);
    }
    private void stopListening() {
        foreground = false; generation++;
        if (Signals.listener == this) Signals.listener = null;
        if (detector != null) detector.stop();
    }
    @Override protected void onStop() {
        stopListening();
        super.onStop();
    }
    @Override public void signal(Source source, String identity) {
        int token = generation;
        main.post(() -> {
            if (!foreground || token != generation || (selected != null && selected != source)) return;
            if (identity != null) {
                LinkedHashSet<String> ids = seen.get(source);
                if (!ids.add(identity)) return;
                if (ids.size() > 512) ids.remove(ids.iterator().next());
            } else if (source == Source.ACCESSIBILITY_EVENT || source == Source.CLIPBOARD) {
                long now = SystemClock.elapsedRealtime(), old = recent.getOrDefault(source, 0L);
                if (now - old < 1500) return;
                recent.put(source, now);
            }
            detections++;
            append(getString(R.string.detected_line, time(), getString(source.label(this))));
            Log.i("ScreenshotDetector", "DETECTED source=" + source.key() + " total=" + detections);
        });
    }
    @Override public void status(Source source, int message) {
        main.post(() -> {
            if (!foreground) return;
            if (selected != null && selected != source) messageIgnored(source);
            else {
            states.get(source).setText(getString(source.label(this)) + " · " + getString(message));
            Log.i("ScreenshotDetector", "STATE source=" + source.key() + " code="
                + getResources().getResourceEntryName(message));
            }
        });
    }
    private void messageIgnored(Source source) {
        states.get(source).setText(getString(source.label(this)) + " · " + getString(R.string.state_disabled));
    }
    private String time() { return DateFormat.getTimeInstance(DateFormat.MEDIUM).format(new Date()); }
    private void append(String line) {
        lines.add(line); if (lines.size() > 200) lines.remove(0); render();
    }
    private void render() {
        count.setText(getString(R.string.event_count, detections));
        log.setText(lines.isEmpty() ? getString(R.string.empty_log) : String.join("\n\n", lines));
    }
    private void diagnostic(int label, boolean accessible) {
        main.post(() -> {
            if (destroyed) return;
            append(getString(R.string.read_check_line, time(), getString(label),
                getString(accessible ? R.string.read_accessible : R.string.read_unavailable)));
            Log.i("ScreenshotDetector", "READ_CHECK route=" + getResources().getResourceEntryName(label)
                + " accessible=" + accessible);
        });
    }
    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request != DOCUMENT || result != RESULT_OK || data == null || data.getData() == null) return;
        Uri uri = data.getData();
        worker.execute(() -> checkDocument(uri));
    }
    @android.annotation.TargetApi(34) // This UI redirects to the state probe on older Android.
    private void checkDocument(Uri uri) {
        ContentResolver resolver = getContentResolver();
        // Real system-granted URI; never log its name, path, or content.
        try (Cursor c = resolver.query(uri, new String[]{DocumentsContract.Document.COLUMN_DOCUMENT_ID},
            null, null, null)) {
            diagnostic(R.string.check_document_query, c != null && c.moveToFirst());
        } catch (RuntimeException e) { diagnostic(R.string.check_document_query, false); }
        try (Cursor c = resolver.query(uri, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            diagnostic(R.string.check_name_query, c != null && c.moveToFirst());
        } catch (RuntimeException e) { diagnostic(R.string.check_name_query, false); }
        try (java.io.InputStream input = resolver.openInputStream(uri)) {
            diagnostic(R.string.check_stream, input != null && input.read() >= 0);
        } catch (Exception e) { diagnostic(R.string.check_stream, false); }
        try (android.content.res.AssetFileDescriptor fd = resolver.openAssetFileDescriptor(uri, "r")) {
            diagnostic(R.string.check_asset, fd != null);
        } catch (Exception e) { diagnostic(R.string.check_asset, false); }
        try (ContentProviderClient client = resolver.acquireContentProviderClient(uri)) {
            try (ParcelFileDescriptor fd = client == null ? null : client.openFile(uri, "r")) {
                diagnostic(R.string.check_client_fd, fd != null);
            }
        } catch (Exception e) { diagnostic(R.string.check_client_fd, false); }
        int mask = 0;
        try (ParcelFileDescriptor fd = resolver.openFileDescriptor(uri, "r")) {
            diagnostic(R.string.check_fd, fd != null);
            if (fd != null) mask = Native.descriptor(fd.getFd());
        } catch (Exception | LinkageError e) { diagnostic(R.string.check_fd, false); }
        int[] labels = {R.string.check_native_open, R.string.check_native_stat,
            R.string.check_native_read, R.string.check_native_pread, R.string.check_native_readv,
            R.string.check_native_mmap, R.string.check_native_fcntl, R.string.check_native_fstat,
            R.string.check_native_statx};
        for (int i = 0; i < labels.length; i++) diagnostic(labels[i], (mask & (1 << i)) != 0);
        try {
            android.graphics.Bitmap thumb = resolver.loadThumbnail(uri, new Size(32, 32), null);
            diagnostic(R.string.check_thumbnail, thumb != null);
            if (thumb != null) thumb.recycle();
        } catch (Exception e) { diagnostic(R.string.check_thumbnail, false); }
    }
    @Override public void onRequestPermissionsResult(int request, String[] permissions, int[] grants) {
        super.onRequestPermissionsResult(request, permissions, grants);
        if (request == PHOTOS) restart();
    }
    @Override protected void onSaveInstanceState(Bundle out) {
        out.putInt("count", detections); out.putStringArrayList("lines", new ArrayList<>(lines));
        out.putInt("source", selected == null ? -1 : selected.ordinal());
        super.onSaveInstanceState(out);
    }
    @Override protected void onDestroy() {
        destroyed = true;
        if (Signals.listener == this) Signals.listener = null;
        foreground = false; if (detector != null) detector.destroy(); worker.shutdown();
        main.removeCallbacksAndMessages(null); super.onDestroy();
    }
}
