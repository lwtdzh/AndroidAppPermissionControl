package io.github.lwtdzh.screenshotdetector;

import android.Manifest;
import android.app.Activity;
import android.content.*;
import android.content.pm.PackageManager;
import android.database.ContentObserver;
import android.database.Cursor;
import android.os.*;
import android.provider.MediaStore;
import java.io.File;
import java.util.*;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Independent registrations and independent baselines for each detector. */
final class Detector {
    private final Activity activity;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final EnumMap<Source, Set<String>> seen = new EnumMap<>(Source.class);
    private final List<FileObserver> watches = new ArrayList<>();
    private final Set<Source> failed = EnumSet.noneOf(Source.class);
    private final Set<Source> busy = EnumSet.noneOf(Source.class);
    private final Activity.ScreenCaptureCallback official = () -> Signals.emit(Source.OFFICIAL, null);
    private final ClipboardManager.OnPrimaryClipChangedListener clip = this::clipboard;
    private ContentObserver observer;
    private BroadcastReceiver receiver;
    private RawCapture raw;
    private ClipboardManager clipboard;
    private boolean registered, active;
    private volatile int generation;
    private Source selected;
    private long nativeWatch;
    private String[] directories = new String[0];
    private final Runnable poll = new Runnable() {
        @Override public void run() {
            if (!active) return;
            for (Source s : new Source[]{Source.MEDIA_POLL, Source.MEDIA_LEGACY, Source.MEDIA_CLIENT})
                if (enabled(s) && !failed.contains(s)) scan(s);
            for (Source s : new Source[]{Source.FILE_POLL, Source.NATIVE_FILES, Source.NATIVE_SYSCALL,
                Source.NATIVE_INOTIFY}) if (enabled(s) && !failed.contains(s)) scan(s);
            if (enabled(Source.NOTIFICATION_LIST) && NotificationDetector.live != null)
                NotificationDetector.live.checkLists();
            if (enabled(Source.ACCESSIBILITY_NODES) && AccessibilityDetector.live != null)
                AccessibilityDetector.live.checkNodes();
            main.postDelayed(this, 1000);
        }
    };
    Detector(Activity activity) {
        this.activity = activity;
        for (Source s : Source.values()) seen.put(s, new HashSet<>());
    }
    private boolean enabled(Source source) { return selected == null || selected == source; }
    private boolean media(Source source) {
        return source == Source.MEDIA_OBSERVER || source == Source.MEDIA_POLL
            || source == Source.MEDIA_LEGACY || source == Source.MEDIA_CLIENT;
    }
    private boolean files(Source source) {
        return source == Source.FILE_OBSERVER || source == Source.FILE_POLL || source == Source.NATIVE_FILES
            || source == Source.NATIVE_SYSCALL || source == Source.NATIVE_INOTIFY;
    }
    void start(Source selection, String customAction) {
        stop();
        selected = selection; active = true;
        int token = ++generation;
        failed.clear(); busy.clear();
        for (Source s : Source.values()) {
            Signals.status(s, enabled(s) ? R.string.state_preparing : R.string.state_disabled);
        }
        if (enabled(Source.OFFICIAL)) {
            try {
                activity.registerScreenCaptureCallback(activity.getMainExecutor(), official);
                registered = true; ready(Source.OFFICIAL);
            } catch (RuntimeException e) { fail(Source.OFFICIAL, e); }
        }
        if (enabled(Source.BINDER)) worker.execute(() -> {
            try {
                int[] codes = FrameworkTransactions.capture();
                main.post(() -> {
                    if (!current(token)) return;
                    try { raw = new RawCapture(activity, codes); ready(Source.BINDER); }
                    catch (Exception e) { fail(Source.BINDER, e); }
                });
            } catch (Exception e) {
                main.post(() -> { if (current(token)) fail(Source.BINDER, e); });
            }
        });
        if (enabled(Source.BROADCAST_DYNAMIC)) {
            receiver = new BroadcastReceiver() {
                @Override public void onReceive(Context c, Intent intent) {
                    BroadcastDetector.receive(Source.BROADCAST_DYNAMIC, intent);
                }
            };
            IntentFilter filter = BroadcastDetector.filter();
            if (!customAction.isBlank()) filter.addAction(customAction.trim());
            try {
                activity.registerReceiver(receiver, filter, Context.RECEIVER_EXPORTED);
                Signals.status(Source.BROADCAST_DYNAMIC, R.string.state_candidate);
            } catch (RuntimeException e) { receiver = null; fail(Source.BROADCAST_DYNAMIC, e); }
        }
        if (enabled(Source.BROADCAST_MANIFEST)) Signals.status(Source.BROADCAST_MANIFEST, R.string.state_candidate);
        if (enabled(Source.CLIPBOARD)) {
            clipboard = activity.getSystemService(ClipboardManager.class);
            try {
                clipboard.addPrimaryClipChangedListener(clip);
                ready(Source.CLIPBOARD);
            } catch (RuntimeException e) { fail(Source.CLIPBOARD, e); }
        }
        services();
        if (NotificationDetector.live != null) NotificationDetector.live.baseline();
        if (AccessibilityDetector.live != null) AccessibilityDetector.live.baseline();
        worker.execute(() -> {
            for (Set<String> ids : seen.values()) ids.clear();
            boolean photos = activity.checkSelfPermission(Manifest.permission.READ_MEDIA_IMAGES)
                == PackageManager.PERMISSION_GRANTED;
            directories = directories();
            for (Source s : Source.values()) {
                if (!enabled(s) || !current(token)) continue;
                if (media(s)) {
                    if (!photos) { state(token, s, R.string.state_photos); continue; }
                    try { seen.get(s).addAll(images(s)); state(token, s, R.string.state_ready); }
                    catch (RuntimeException e) { error(token, s, e); }
                } else if (files(s)) {
                    if (!Environment.isExternalStorageManager() && !photos) {
                        state(token, s, R.string.state_files); continue;
                    }
                    try {
                        if (s == Source.NATIVE_INOTIFY) {
                            nativeWatch = Native.watch(directories);
                            if (nativeWatch == 0) throw new SecurityException();
                        } else seen.get(s).addAll(fileList(s));
                        state(token, s, R.string.state_ready);
                    } catch (RuntimeException | LinkageError e) { error(token, s, e); }
                }
            }
            main.post(() -> {
                if (!current(token)) return;
                if (enabled(Source.MEDIA_OBSERVER) && !failed.contains(Source.MEDIA_OBSERVER) && photos) {
                    observer = new ContentObserver(main) {
                        @Override public void onChange(boolean selfChange) { scan(Source.MEDIA_OBSERVER); }
                    };
                    try {
                        activity.getContentResolver().registerContentObserver(
                            MediaStore.Images.Media.EXTERNAL_CONTENT_URI, true, observer);
                        scan(Source.MEDIA_OBSERVER);
                    } catch (RuntimeException e) { fail(Source.MEDIA_OBSERVER, e); }
                }
                if (enabled(Source.FILE_OBSERVER) && !failed.contains(Source.FILE_OBSERVER)
                    && (photos || Environment.isExternalStorageManager())) {
                    for (String directory : directories) {
                        FileObserver watch = new FileObserver(new File(directory),
                            FileObserver.CLOSE_WRITE | FileObserver.MOVED_TO) {
                            @Override public void onEvent(int event, String path) {
                                if (path != null && Signals.screenshotFile(directory + "/" + path))
                                    Signals.emit(Source.FILE_OBSERVER, directory + "/" + path);
                            }
                        };
                        watch.startWatching(); watches.add(watch);
                    }
                    if (watches.isEmpty()) Signals.status(Source.FILE_OBSERVER, R.string.state_files);
                }
                main.post(poll);
            });
        });
    }
    void services() {
        for (Source s : new Source[]{Source.NOTIFICATION_EVENT, Source.NOTIFICATION_LIST})
            if (enabled(s)) Signals.status(s, NotificationDetector.live == null
                ? R.string.state_notifications : R.string.state_ready);
        for (Source s : new Source[]{Source.ACCESSIBILITY_EVENT, Source.ACCESSIBILITY_NODES})
            if (enabled(s)) Signals.status(s, AccessibilityDetector.live == null
                ? R.string.state_accessibility : R.string.state_ready);
    }
    private void clipboard() {
        if (!active || !enabled(Source.CLIPBOARD) || !activity.hasWindowFocus()) return;
        try {
            if (Signals.clip(activity, clipboard.getPrimaryClip()))
                Signals.emit(Source.CLIPBOARD, null);
        } catch (RuntimeException e) { fail(Source.CLIPBOARD, e); }
    }
    private List<String> images(Source source) {
        ContentResolver resolver = activity.getContentResolver();
        String[] projection = {"_id", "_display_name", "relative_path"};
        Cursor result;
        if (source == Source.MEDIA_LEGACY) {
            result = resolver.query(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, projection,
                "is_pending=0", null, "_id DESC");
        } else {
            Bundle args = new Bundle();
            args.putString(ContentResolver.QUERY_ARG_SQL_SELECTION, "is_pending=0");
            args.putStringArray(ContentResolver.QUERY_ARG_SORT_COLUMNS, new String[]{"_id"});
            args.putInt(ContentResolver.QUERY_ARG_SORT_DIRECTION, ContentResolver.QUERY_SORT_DIRECTION_DESCENDING);
            args.putInt(ContentResolver.QUERY_ARG_LIMIT, 256);
            if (source == Source.MEDIA_CLIENT) {
                try (ContentProviderClient client = resolver.acquireContentProviderClient(
                    MediaStore.Images.Media.EXTERNAL_CONTENT_URI)) {
                    if (client == null) throw new IllegalStateException();
                    result = client.query(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, projection, args, null);
                } catch (RemoteException e) { throw new IllegalStateException(e); }
            } else result = resolver.query(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, projection, args, null);
        }
        ArrayList<String> images = new ArrayList<>();
        if (result == null) throw new IllegalStateException();
        try (Cursor cursor = result) {
            int count = 0;
            while (count++ < 256 && cursor.moveToNext())
                if (Signals.screenshot(cursor.getString(1)) || Signals.screenshot(cursor.getString(2)))
                    images.add(cursor.getString(0));
        }
        return images;
    }
    private String[] directories() {
        Set<String> paths = new LinkedHashSet<>();
        String root = Environment.getExternalStorageDirectory().getAbsolutePath();
        for (String base : new String[]{"DCIM", "Pictures", "Download"}) {
            File dir = new File(root, base);
            if (dir.isDirectory()) paths.add(dir.getAbsolutePath());
            File[] children = dir.listFiles();
            if (children != null) for (File child : children)
                if (child.isDirectory() && Signals.screenshot(child.getName())) paths.add(child.getAbsolutePath());
            // Keep conventional paths even when directory metadata is filtered by the module.
            paths.add(root + "/" + base + "/Screenshots");
        }
        return paths.toArray(new String[0]);
    }
    private List<String> fileList(Source source) {
        List<String> found = new ArrayList<>();
        boolean accessible = false;
        for (String directory : directories) {
            if (source == Source.NATIVE_FILES || source == Source.NATIVE_SYSCALL) {
                String[] list = Native.files(directory, source == Source.NATIVE_SYSCALL);
                if (list != null) {
                    accessible = true;
                    for (String path : list) if (Signals.screenshotFile(path)) found.add(path);
                }
            } else {
                File[] list = new File(directory).listFiles();
                if (list != null) {
                    accessible = true;
                    for (File path : list) if (path.isFile() && path.length() > 0
                        && Signals.screenshotFile(path.toString())) found.add(path.toString());
                }
            }
        }
        if (!accessible) throw new SecurityException();
        return found;
    }
    private void scan(Source source) {
        if (!active || busy.contains(source)) return;
        busy.add(source);
        int token = generation;
        worker.execute(() -> {
            try {
                List<String> found = source == Source.NATIVE_INOTIFY
                    ? Arrays.asList(Native.events(nativeWatch))
                    : media(source) ? images(source) : fileList(source);
                ArrayList<String> fresh = new ArrayList<>();
                for (String id : found) if ((source != Source.NATIVE_INOTIFY || Signals.screenshotFile(id))
                    && seen.get(source).add(id)) fresh.add(id);
                main.post(() -> {
                    if (!current(token)) return;
                    busy.remove(source);
                    for (String id : fresh) Signals.emit(source, id);
                });
            } catch (RuntimeException | LinkageError e) { error(token, source, e); }
        });
    }
    private boolean current(int token) { return active && generation == token; }
    private void ready(Source source) { Signals.status(source, R.string.state_ready); }
    private void state(int token, Source source, int status) {
        main.post(() -> {
            if (current(token)) {
                if (status != R.string.state_ready) failed.add(source);
                Signals.status(source, status);
            }
        });
    }
    private void error(int token, Source source, Throwable error) {
        main.post(() -> { if (current(token)) { busy.remove(source); fail(source, error); } });
    }
    private void fail(Source source, Throwable error) {
        failed.add(source);
        Signals.status(source, error instanceof SecurityException ? R.string.state_permission : R.string.state_unsupported);
        android.util.Log.w("ScreenshotDetector", "UNAVAILABLE source=" + source.key()
            + " reason=" + error.getClass().getSimpleName());
    }
    void stop() {
        active = false; generation++; main.removeCallbacksAndMessages(null);
        if (registered) {
            try { activity.unregisterScreenCaptureCallback(official); } catch (RuntimeException ignored) { }
            registered = false;
        }
        if (raw != null) { try { raw.close(); } catch (Exception ignored) { } raw = null; }
        if (observer != null) {
            try { activity.getContentResolver().unregisterContentObserver(observer); }
            catch (RuntimeException ignored) { }
            observer = null;
        }
        if (receiver != null) { activity.unregisterReceiver(receiver); receiver = null; }
        if (clipboard != null) { clipboard.removePrimaryClipChangedListener(clip); clipboard = null; }
        for (FileObserver watch : watches) watch.stopWatching();
        watches.clear();
        worker.execute(() -> { if (nativeWatch != 0) { Native.close(nativeWatch); nativeWatch = 0; } });
    }
    void destroy() { stop(); worker.shutdown(); }
}
