package io.github.lwtdzh.screenshotshield;

import android.app.AndroidAppHelper;
import android.content.ContentResolver;
import android.database.ContentObserver;
import android.database.Cursor;
import android.net.Uri;
import android.os.Bundle;
import android.os.Build;
import android.util.Log;
import java.io.File;
import java.io.FileNotFoundException;
import java.lang.reflect.Method;
import java.util.Collections;
import java.util.Map;
import java.util.WeakHashMap;
import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

public final class ShieldModule implements IXposedHookLoadPackage {
    private static final String TAG = "ScreenshotShield";
    private static boolean installed;
    private static final ThreadLocal<Boolean> INTERNAL = ThreadLocal.withInitial(() -> false);
    private static final ThreadLocal<Integer> QUERY_DEPTH = ThreadLocal.withInitial(() -> 0);
    private static final ThreadLocal<Integer> MEDIA_DISPATCH_DEPTH = ThreadLocal.withInitial(() -> 0);
    private static final Map<ContentObserver, MediaObservation> MEDIA_OBSERVERS =
        Collections.synchronizedMap(new WeakHashMap<>());
    private static int loggedBlocks;
    private static final java.util.Set<Method> BROADCAST_CALLBACKS =
        Collections.synchronizedSet(new java.util.HashSet<>());

    @Override public void handleLoadPackage(XC_LoadPackage.LoadPackageParam load) {
        // No package list. Installation is once per process and Vector determines scope.
        synchronized (ShieldModule.class) {
            if (installed) return;
            installed = true;
        }
        Log.i(TAG, "install process=" + load.processName + " sdk=" + Build.VERSION.SDK_INT);
        screenshotCallbacks(load.classLoader);
        mediaQueries(load.classLoader);
        mediaNotifications();
        fileReads();
        broadcasts(load.classLoader);
        SignalHooks.install(load.classLoader);
        try {
            System.loadLibrary("shield");
            Log.i(TAG, "native library loaded");
        } catch (Throwable error) {
            Log.e(TAG, "native layer unavailable; Java hooks remain active", error);
        }
    }
    private static void block(String kind) {
        synchronized (ShieldModule.class) {
            // Never log paths, image contents, account data or an unbounded stream.
            if (loggedBlocks++ < 40) Log.i(TAG, "blocked " + kind);
        }
    }
    private static int hook(Class<?> type, String method, XC_MethodHook callback) {
        if (type == null) return 0;
        try {
            return XposedBridge.hookAllMethods(type, method, callback).size();
        } catch (Throwable error) {
            Log.w(TAG, "cannot hook " + type.getName() + "." + method + ": " + error.getClass().getSimpleName());
            return 0;
        }
    }
    private static Class<?> optional(String name, ClassLoader loader) {
        return XposedHelpers.findClassIfExists(name, loader);
    }
    private static final XC_MethodHook SILENT_VOID = new XC_MethodHook() {
        @Override protected void beforeHookedMethod(MethodHookParam p) {
            block("official callback");
            p.setResult(null);
        }
    };
    private static void screenshotCallbacks(ClassLoader loader) {
        hook(android.app.Activity.class, "registerScreenCaptureCallback", SILENT_VOID);
        hook(android.app.Activity.class, "unregisterScreenCaptureCallback", SILENT_VOID);
        // Also intercept callers which bypass the public Activity API and use its controller/Binder.
        hook(optional("android.app.ScreenCaptureCallbackHandler", loader), "registerScreenCaptureCallback", SILENT_VOID);
        hook(optional("android.app.ScreenCaptureCallbackHandler", loader), "unregisterScreenCaptureCallback", SILENT_VOID);
        hook(optional("android.app.ScreenCaptureCallbackHandler$ScreenCaptureObserver", loader), "onScreenCaptured", SILENT_VOID);
        for (String name : new String[]{
            "android.app.ActivityClient", "android.app.IActivityTaskManager$Stub$Proxy"
        }) {
            hook(optional(name, loader), "registerScreenCaptureObserver", SILENT_VOID);
            hook(optional(name, loader), "unregisterScreenCaptureObserver", SILENT_VOID);
        }
        Class<?> stub = optional("android.app.IActivityTaskManager$Stub", loader);
        if (stub == null) return;
        java.util.Set<Integer> codes = new java.util.HashSet<>();
        for (String method : new String[]{"registerScreenCaptureObserver", "unregisterScreenCaptureObserver"}) {
            try { codes.add(XposedHelpers.getStaticIntField(stub, "TRANSACTION_" + method)); }
            catch (Throwable ignored) {}
        }
        Map<Object, String> descriptors = Collections.synchronizedMap(new WeakHashMap<>());
        hook(optional("android.os.BinderProxy", loader), "transact", new XC_MethodHook() {
            @Override protected void beforeHookedMethod(MethodHookParam p) throws Throwable {
                if (INTERNAL.get() || !codes.contains((Integer) p.args[0])) return;
                android.os.IBinder binder = (android.os.IBinder) p.thisObject;
                String descriptor = descriptors.get(binder);
                if (descriptor == null) {
                    INTERNAL.set(true);
                    try { descriptor = binder.getInterfaceDescriptor(); }
                    finally { INTERNAL.set(false); }
                    if (descriptor != null) descriptors.put(binder, descriptor);
                }
                if (!"android.app.IActivityTaskManager".equals(descriptor)) return;
                android.os.Parcel reply = (android.os.Parcel) p.args[2];
                if (reply != null) {
                    reply.setDataSize(0);
                    reply.setDataPosition(0);
                    reply.writeNoException(); // Both AIDL methods return void.
                    reply.setDataPosition(0);
                }
                block("direct screenshot Binder");
                p.setResult(true);
            }
        });
    }
    private static Uri uri(Object[] args) {
        for (Object arg : args) if (arg instanceof Uri) return (Uri) arg;
        return null;
    }
    private static void mediaQueries(ClassLoader loader) {
        XC_MethodHook query = new XC_MethodHook() {
            @Override protected void beforeHookedMethod(MethodHookParam p) {
                if (INTERNAL.get()) return;
                Uri target = uri(p.args);
                if (!Rules.media(target) && !Rules.document(target)) return;
                int depth = QUERY_DEPTH.get();
                p.setObjectExtra("shield_query_depth", depth);
                QUERY_DEPTH.set(depth + 1);
                // Resolver -> client -> Binder proxy can all be hooked in the same call.
                if (depth != 0) return;
                Class<?>[] types = ((Method) p.method).getParameterTypes();
                if (!Rules.mediaRows(target)) {
                    for (int i = 0; i < types.length; i++) {
                        if (types[i] != String[].class || (i > 0 && types[i - 1] != Uri.class)) continue;
                        String[] projection = (String[]) p.args[i];
                        if (projection == null || java.util.Arrays.asList(projection).contains("*")) return;
                        java.util.List<String> expanded = new java.util.ArrayList<>(java.util.Arrays.asList(projection));
                        for (String column : Rules.document(target)
                            ? new String[]{"_display_name", "document_id"} : new String[]{"image_id"}) {
                            if (!expanded.contains(column)) expanded.add(column);
                        }
                        if (expanded.size() != projection.length) {
                            p.setObjectExtra("shield_projection_size", projection.length);
                            p.args[i] = expanded.toArray(new String[0]);
                        }
                        return;
                    }
                    return;
                }
                // API 26+ Bundle form, including direct provider and ContentProviderClient.
                for (int i = 0; i < types.length; i++) {
                    if (types[i] == Bundle.class) {
                        Bundle options = p.args[i] == null ? new Bundle() : new Bundle((Bundle) p.args[i]);
                        String selection = options.getString(ContentResolver.QUERY_ARG_SQL_SELECTION);
                        options.putString(ContentResolver.QUERY_ARG_SQL_SELECTION, Rules.combine(selection));
                        p.args[i] = options;
                        return;
                    }
                }
                // Legacy (Uri, projection, selection, selectionArgs, sortOrder, ...).
                for (int i = 0; i + 2 < types.length; i++) {
                    if (types[i] == Uri.class && types[i + 1] == String[].class && types[i + 2] == String.class) {
                        p.args[i + 2] = Rules.combine((String) p.args[i + 2]);
                        return;
                    }
                }
            }
            @Override protected void afterHookedMethod(MethodHookParam p) {
                Object depth = p.getObjectExtra("shield_query_depth");
                if (depth instanceof Integer) {
                    QUERY_DEPTH.set((Integer) depth);
                    if ((Integer) depth != 0) return;
                }
                if (INTERNAL.get() || p.hasThrowable() || !(p.getResult() instanceof Cursor)) return;
                Uri target = uri(p.args);
                if (Rules.content(target)) {
                    Cursor original = (Cursor) p.getResult();
                    try {
                        Cursor filtered = FilteredCursor.wrap(original, Rules.document(target)
                            || (Rules.media(target) && !Rules.mediaRows(target)) ? row -> {
                                int column = row.getColumnIndex("document_id");
                                if (column >= 0) {
                                    Uri image = Rules.documentImage(Uri.withAppendedPath(target, row.getString(column)));
                                    if (isScreenshotItem(image)) return true;
                                }
                                column = row.getColumnIndex("image_id");
                                return column >= 0 && isScreenshotItem(Uri.parse(
                                    "content://media/external/images/media/" + row.getLong(column)));
                            } : null);
                        Object size = p.getObjectExtra("shield_projection_size");
                        p.setResult(size instanceof Integer ? new ProjectedCursor(filtered, (Integer) size) : filtered);
                    } catch (Throwable error) {
                        Log.w(TAG, "cursor filter failed: " + error.getClass().getSimpleName());
                    }
                }
            }
        };
        hook(ContentResolver.class, "query", query);
        hook(android.content.ContentProviderClient.class, "query", query);
        hook(optional("android.content.ContentProviderProxy", loader), "query", query);
        hook(optional("android.content.IContentProvider$Stub$Proxy", loader), "query", query);
        XC_MethodHook opening = new XC_MethodHook() {
            @Override protected void beforeHookedMethod(MethodHookParam p) {
                if (INTERNAL.get()) return;
                Uri target = uri(p.args);
                if (screenshotContent(target)) {
                    block("content open");
                    p.setThrowable(new FileNotFoundException("Not available"));
                }
            }
        };
        for (Class<?> type : new Class<?>[]{ContentResolver.class, android.content.ContentProviderClient.class,
            optional("android.content.ContentProviderProxy", loader),
            optional("android.content.IContentProvider$Stub$Proxy", loader)}) {
            for (String method : new String[]{"openInputStream", "openFileDescriptor", "openAssetFileDescriptor",
                "openTypedAssetFileDescriptor", "openFile", "openAssetFile", "openTypedAssetFile", "loadThumbnail"}) {
                hook(type, method, opening);
            }
        }
    }
    static boolean screenshotContent(Uri target) {
        if (!Rules.content(target)) return target != null && "file".equals(target.getScheme())
            && Rules.file(target.getPath());
        if (Rules.screenshotUri(target) || isScreenshotItem(Rules.documentImage(target))) return true;
        if (Rules.mediaRows(target)) return isScreenshotItem(target);
        boolean previous = INTERNAL.get();
        INTERNAL.set(true);
        try {
            android.app.Application app = AndroidAppHelper.currentApplication();
            if (app != null) try (Cursor cursor = app.getContentResolver().query(target, null, null, null, null)) {
                if (cursor != null && cursor.moveToFirst()) {
                    for (String name : new String[]{"_display_name", "_data", "relative_path", "document_id"}) {
                        int column = cursor.getColumnIndex(name);
                        if (column >= 0 && Rules.screenshot(cursor.getString(column))) return true;
                    }
                    int column = cursor.getColumnIndex("image_id");
                    if (column >= 0) return isScreenshotItem(Uri.parse(
                        "content://media/external/images/media/" + cursor.getLong(column)));
                }
            }
        } catch (RuntimeException ignored) {
        } finally { INTERNAL.set(previous); }
        return false;
    }
    private static boolean isScreenshotItem(Uri target) {
        if (!Rules.mediaRows(target)) return false;
        String segment = target.getLastPathSegment();
        if (segment == null || !segment.matches("[0-9]+")) return false;
        boolean previous = INTERNAL.get();
        INTERNAL.set(true);
        try {
            android.app.Application app = AndroidAppHelper.currentApplication();
            if (app == null) return false;
            String[] columns = Build.VERSION.SDK_INT >= 29
                ? new String[]{"_display_name", "_data", "relative_path"}
                : new String[]{"_display_name", "_data"};
            try (Cursor cursor = app.getContentResolver().query(target, columns, null, null, null)) {
                if (cursor != null && cursor.moveToFirst()) {
                    for (int i = 0; i < columns.length; i++) if (Rules.screenshot(cursor.getString(i))) return true;
                }
            }
        } catch (RuntimeException ignored) {
            // A denied provider access must not crash an unrelated callback dispatch.
        } finally {
            INTERNAL.set(previous);
        }
        return false;
    }
    private static void mediaNotifications() {
        hook(ContentResolver.class, "registerContentObserver", new XC_MethodHook() {
            @Override protected void beforeHookedMethod(MethodHookParam p) {
                Uri target = uri(p.args);
                if (Rules.mediaObserved(target)) {
                    for (Object arg : p.args) if (arg instanceof ContentObserver) {
                        synchronized (MEDIA_OBSERVERS) {
                            MediaObservation observation = MEDIA_OBSERVERS.get((ContentObserver) arg);
                            if (observation == null) {
                                observation = new MediaObservation((ContentResolver) p.thisObject);
                                MEDIA_OBSERVERS.put((ContentObserver) arg, observation);
                            }
                            observation.observe(target);
                        }
                    }
                }
            }
        });
        hook(ContentResolver.class, "unregisterContentObserver", new XC_MethodHook() {
            @Override protected void afterHookedMethod(MethodHookParam p) {
                if (!p.hasThrowable()) for (Object arg : p.args) {
                    if (arg instanceof ContentObserver) MEDIA_OBSERVERS.remove(arg);
                }
            }
        });
        // All real observer notifications pass through final dispatchChange overloads.
        hook(ContentObserver.class, "dispatchChange", new XC_MethodHook() {
            @Override protected void beforeHookedMethod(MethodHookParam p) {
                if (INTERNAL.get() || MEDIA_DISPATCH_DEPTH.get() != 0) return;
                MEDIA_DISPATCH_DEPTH.set(1);
                p.setObjectExtra("mediaDispatch", true);
                MediaObservation observation = MEDIA_OBSERVERS.get((ContentObserver) p.thisObject);
                boolean watched = observation != null;
                Boolean ordinaryChanged = null;
                boolean sawUri = false;
                for (int i = 0; i < p.args.length; i++) {
                    Object arg = p.args[i];
                    if (arg instanceof Uri) {
                        sawUri = true;
                        Uri target = (Uri) arg;
                        if (unidentifiedMedia(target, watched)) {
                            if (ordinaryChanged == null) ordinaryChanged = observation.changed();
                            if (!ordinaryChanged) { block("unidentified media notification"); p.setResult(null); return; }
                        } else if (suppress(target, watched)) {
                            block("media notification"); p.setResult(null); return;
                        }
                    } else if (arg instanceof Uri[]) {
                        Uri[] original = (Uri[]) arg;
                        java.util.ArrayList<Uri> visible = new java.util.ArrayList<>();
                        for (Uri target : original) {
                            if (unidentifiedMedia(target, watched)) {
                                if (ordinaryChanged == null) ordinaryChanged = observation.changed();
                                if (ordinaryChanged) visible.add(target);
                            } else if (!suppress(target, watched)) visible.add(target);
                        }
                        sawUri |= original.length > 0;
                        if (visible.isEmpty() && watched) { block("media notification"); p.setResult(null); return; }
                        p.args[i] = visible.toArray(new Uri[0]);
                    }
                }
                if (!sawUri && watched && !observation.changed()) {
                    block("unidentified media notification"); p.setResult(null);
                }
            }
            @Override protected void afterHookedMethod(MethodHookParam p) {
                if (Boolean.TRUE.equals(p.getObjectExtra("mediaDispatch"))) MEDIA_DISPATCH_DEPTH.set(0);
            }
        });
    }
    private static boolean unidentifiedMedia(Uri target, boolean watched) {
        if (!watched) return false;
        if (target == null) return true;
        if (Rules.screenshotUri(target) || !Rules.mediaObserved(target)) return false;
        return !Rules.media(target) || !target.getLastPathSegment().matches("[0-9]+");
    }
    /** Compare only visible rows when the provider supplies no item identity.
     * A screenshot-only change never changes this snapshot. */
    private static final class MediaObservation {
        private final ContentResolver resolver;
        private final Map<Uri, Map<String, java.util.List<String>>> snapshots = new java.util.HashMap<>();
        MediaObservation(ContentResolver resolver) { this.resolver = resolver; }
        synchronized void observe(Uri target) { snapshots.put(target, snapshot(target)); }
        synchronized boolean changed() {
            boolean changed = false;
            for (Map.Entry<Uri, Map<String, java.util.List<String>>> entry : snapshots.entrySet()) {
                Map<String, java.util.List<String>> next = snapshot(entry.getKey());
                // Missing permission or a failed query cannot prove a normal change.
                if (next != null && entry.getValue() != null && !next.equals(entry.getValue())) changed = true;
                entry.setValue(next);
            }
            return changed;
        }
        private Map<String, java.util.List<String>> snapshot(Uri observed) {
            Uri target = observed;
            if (!Rules.mediaRows(target)) {
                String volume = target.getPathSegments().isEmpty() ? "external" : target.getPathSegments().get(0);
                target = new Uri.Builder().scheme("content").authority(target.getAuthority())
                    .appendPath(volume).appendPath("file").build();
            }
            java.util.ArrayList<String> columns = new java.util.ArrayList<>(java.util.Arrays.asList(
                "_id", "_display_name", "_data", "_size", "date_added", "date_modified"));
            if (Build.VERSION.SDK_INT >= 29) columns.add("relative_path");
            if (Build.VERSION.SDK_INT >= 30) columns.add("generation_modified");
            boolean previous = INTERNAL.get();
            INTERNAL.set(true);
            try (Cursor cursor = resolver.query(target, columns.toArray(new String[0]),
                                                 Rules.exclusion(), null, null)) {
                if (cursor == null) return null;
                Map<String, java.util.List<String>> result = new java.util.HashMap<>();
                while (cursor.moveToNext()) {
                    java.util.ArrayList<String> row = new java.util.ArrayList<>();
                    for (int i = 1; i < columns.size(); i++) row.add(cursor.getString(i));
                    result.put(cursor.getString(0), row);
                }
                return result;
            } catch (RuntimeException ignored) {
                return null;
            } finally { INTERNAL.set(previous); }
        }
    }
    private static boolean suppress(Uri target, boolean watched) {
        if (target == null) return watched;
        if (Rules.screenshotUri(target)) return true;
        if (Rules.mediaObserved(target) && !Rules.media(target)) return watched;
        if (!Rules.media(target)) return Rules.document(target) && screenshotContent(target);
        String segment = target.getLastPathSegment();
        if (segment == null || !segment.matches("[0-9]+")) return watched;
        return isScreenshotItem(target);
    }
    private static void fileReads() {
        XC_MethodHook hiddenFile = new XC_MethodHook() {
            @Override protected void beforeHookedMethod(MethodHookParam p) {
                File file = (File) p.thisObject;
                if (!Rules.file(file.getPath())) return;
                Class<?> result = ((Method) p.method).getReturnType();
                if (result == boolean.class) p.setResult(false);
                else if (result == long.class) p.setResult(0L);
                else p.setResult(null);
            }
        };
        for (String method : new String[]{"exists", "isFile", "isDirectory", "canRead", "length", "lastModified",
            "list", "listFiles"}) hook(File.class, method, hiddenFile);
        for (String method : new String[]{"list", "listFiles"}) hook(File.class, method, new XC_MethodHook() {
            @Override protected void afterHookedMethod(MethodHookParam p) {
                if (p.hasThrowable()) return;
                if (p.getResult() instanceof String[]) {
                    p.setResult(java.util.Arrays.stream((String[]) p.getResult())
                        .filter(name -> !Rules.file(new File((File) p.thisObject, name).getPath())).toArray(String[]::new));
                } else if (p.getResult() instanceof File[]) {
                    p.setResult(java.util.Arrays.stream((File[]) p.getResult())
                        .filter(file -> !Rules.file(file.getPath())).toArray(File[]::new));
                }
            }
        });
        XC_MethodHook stream = new XC_MethodHook() {
            @Override protected void beforeHookedMethod(MethodHookParam p) {
                for (Object arg : p.args) {
                    String path = arg instanceof File ? ((File) arg).getPath() : arg instanceof String ? (String) arg : null;
                    if (Rules.file(path)) {
                        block("Java file read");
                        p.setThrowable(new FileNotFoundException("Not available"));
                        return;
                    }
                }
            }
        };
        XposedBridge.hookAllConstructors(java.io.FileInputStream.class, stream);
        XposedBridge.hookAllConstructors(java.io.RandomAccessFile.class, stream);
        // FileObserver is backed by native inotify. Native event filtering also handles NIO/JNI users.
    }
    private static void broadcasts(ClassLoader loader) {
        // Framework dispatchers can inline Args.getRunnable(). Hook the app's
        // concrete callback at registration too, preserving framework completion.
        XC_MethodHook registration = new XC_MethodHook() {
            @Override protected void beforeHookedMethod(MethodHookParam p) {
                for (Object argument : p.args) {
                    if (!(argument instanceof android.content.BroadcastReceiver)) continue;
                    for (Class<?> type = argument.getClass(); type != null; type = type.getSuperclass()) {
                        for (Method method : type.getDeclaredMethods()) {
                            if (!method.getName().equals("onReceive")
                                || java.lang.reflect.Modifier.isAbstract(method.getModifiers())
                                || !BROADCAST_CALLBACKS.add(method)) continue;
                            XposedBridge.hookMethod(method, new XC_MethodHook() {
                                @Override protected void beforeHookedMethod(MethodHookParam callback) {
                                    for (Object value : callback.args) {
                                        if (value instanceof android.content.Intent
                                            && Rules.screenshotBroadcast(((android.content.Intent) value).getAction())) {
                                            block("registered screenshot broadcast");
                                            callback.setResult(null);
                                            return;
                                        }
                                    }
                                }
                            });
                        }
                    }
                }
            }
        };
        hook(optional("android.app.LoadedApk", loader), "getReceiverDispatcher", registration);
        hook(optional("android.app.ContextImpl", loader), "registerReceiverInternal", registration);
        Class<?> argsClass = optional("android.app.LoadedApk$ReceiverDispatcher$Args", loader);
        XC_MethodHook delivery = new XC_MethodHook() {
            @Override protected void beforeHookedMethod(MethodHookParam p) {
                Object intent = null;
                for (String field : new String[]{"mCurIntent", "mIntent"}) {
                    try { intent = XposedHelpers.getObjectField(p.thisObject, field); break; }
                    catch (Throwable ignored) {}
                }
                if (intent instanceof android.content.Intent
                    && Rules.screenshotBroadcast(((android.content.Intent) intent).getAction())
                    && p.thisObject instanceof android.content.BroadcastReceiver.PendingResult) {
                    // Complete the system's pending delivery even for ordered broadcasts.
                    android.content.BroadcastReceiver.PendingResult pending =
                        (android.content.BroadcastReceiver.PendingResult) p.thisObject;
                    if ("getRunnable".equals(p.method.getName())) {
                        p.setResult((Runnable) () -> { pending.finish(); block("screenshot broadcast"); });
                    } else {
                        pending.finish();
                        block("screenshot broadcast");
                        p.setResult(null);
                    }
                }
            }
        };
        // New Android releases return a lambda rather than implementing Runnable on Args.
        hook(argsClass, "run", delivery);
        hook(argsClass, "getRunnable", delivery);
        hook(optional("android.app.ActivityThread", loader), "handleReceiver", new XC_MethodHook() {
            @Override protected void beforeHookedMethod(MethodHookParam p) {
                if (p.args.length == 0 || !(p.args[0] instanceof android.content.BroadcastReceiver.PendingResult)) return;
                Object data = p.args[0];
                Object intent;
                try { intent = XposedHelpers.getObjectField(data, "intent"); }
                catch (Throwable ignored) { return; }
                if (intent instanceof android.content.Intent
                    && Rules.screenshotBroadcast(((android.content.Intent) intent).getAction())) {
                    ((android.content.BroadcastReceiver.PendingResult) data).finish();
                    block("manifest screenshot broadcast");
                    p.setResult(null);
                }
            }
        });
    }
}
