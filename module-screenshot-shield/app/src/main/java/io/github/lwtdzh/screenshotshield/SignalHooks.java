package io.github.lwtdzh.screenshotshield;

import android.accessibilityservice.AccessibilityService;
import android.app.Notification;
import android.content.ClipData;
import android.content.ClipDescription;
import android.content.ClipboardManager;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;
import java.lang.reflect.Array;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;

/** Filters metadata at app callbacks/getters, retaining framework cache/ranking updates. */
final class SignalHooks {
    private static final ThreadLocal<Boolean> INTERNAL = ThreadLocal.withInitial(() -> false);
    private static final Set<Method> CALLBACKS = Collections.synchronizedSet(new HashSet<>());
    private static final Set<String> HIDDEN_NOTIFICATION_KEYS = ConcurrentHashMap.newKeySet();

    private static void hook(Class<?> type, String name, XC_MethodHook callback) {
        if (type != null) XposedBridge.hookAllMethods(type, name, callback);
    }
    private static Class<?> optional(String name, ClassLoader loader) {
        return XposedHelpers.findClassIfExists(name, loader);
    }
    private static boolean source(CharSequence owner) {
        if (owner == null) return false;
        String name = owner.toString().toLowerCase(java.util.Locale.ROOT);
        return name.equals("android") || name.equals("com.android.systemui")
            || name.endsWith(".screenshot") || name.endsWith(".screencapture")
            || name.equals("com.vivo.smartshot");
    }
    private static String simple(CharSequence value) {
        if (value == null) return null;
        String text = value.toString();
        return text.substring(Math.max(text.lastIndexOf('.'), text.lastIndexOf('/')) + 1);
    }
    private static boolean description(ClipDescription clip) {
        return clip != null && clip.hasMimeType("image/*")
            && Rules.screenshot(clip.getLabel() == null ? null : clip.getLabel().toString());
    }
    private static boolean clip(ClipData clip) {
        if (clip == null) return false;
        if (description(clip.getDescription())) return true;
        for (int i = 0; i < clip.getItemCount(); i++) {
            android.net.Uri uri = clip.getItemAt(i).getUri();
            if (uri != null && ShieldModule.screenshotContent(uri)) return true;
        }
        return false;
    }
    private static boolean clipboardHidden(ClipboardManager manager) {
        if (INTERNAL.get()) return false;
        INTERNAL.set(true);
        try {
            // Description is metadata only: never fetch clipboard content merely to answer
            // hasPrimaryClip or deliver a listener (which could display Android's paste toast).
            return description(manager.getPrimaryClipDescription());
        } catch (RuntimeException ignored) { return false; }
        finally { INTERNAL.set(false); }
    }
    private static boolean notification(StatusBarNotification sbn) {
        if (sbn == null) return false;
        if (HIDDEN_NOTIFICATION_KEYS.contains(sbn.getKey())) return true;
        Notification value = sbn.getNotification();
        boolean hidden = false;
        if (source(sbn.getPackageName()) && value != null) {
            for (String key : new String[]{Notification.EXTRA_TITLE, Notification.EXTRA_TEXT,
                Notification.EXTRA_SUB_TEXT, Notification.EXTRA_BIG_TEXT, Notification.EXTRA_SUMMARY_TEXT}) {
                CharSequence text = value.extras.getCharSequence(key);
                if (text != null && Rules.screenshot(text.toString())) hidden = true;
            }
            CharSequence[] lines = value.extras.getCharSequenceArray(Notification.EXTRA_TEXT_LINES);
            if (lines != null) for (CharSequence line : lines) {
                if (line != null && Rules.screenshot(line.toString())) hidden = true;
            }
            hidden |= Rules.screenshot(value.getChannelId());
        }
        if (hidden) {
            if (HIDDEN_NOTIFICATION_KEYS.size() > 512) HIDDEN_NOTIFICATION_KEYS.clear();
            HIDDEN_NOTIFICATION_KEYS.add(sbn.getKey());
        }
        return hidden;
    }
    private static boolean event(AccessibilityEvent value) {
        if (value == null || !source(value.getPackageName())) return false;
        if (Rules.screenshot(simple(value.getClassName()))) return true;
        if (value.getContentDescription() != null
            && Rules.screenshot(value.getContentDescription().toString())) return true;
        for (CharSequence text : value.getText()) if (text != null && Rules.screenshot(text.toString())) return true;
        return false;
    }
    private static boolean node(AccessibilityNodeInfo root) {
        if (root == null) return false;
        boolean previous = INTERNAL.get();
        INTERNAL.set(true);
        try { return node(root, new HashSet<>(), new int[]{256}); }
        catch (RuntimeException ignored) { return false; }
        finally { INTERNAL.set(previous); }
    }
    private static boolean node(AccessibilityNodeInfo value, Set<AccessibilityNodeInfo> seen, int[] remaining) {
        if (value == null || remaining[0]-- <= 0 || !seen.add(value)) return false;
        if (source(value.getPackageName())) {
            if (Rules.screenshot(simple(value.getClassName()))
                || Rules.screenshot(simple(value.getViewIdResourceName()))
                || (value.getContentDescription() != null && Rules.screenshot(value.getContentDescription().toString()))
                || (value.getText() != null && Rules.screenshot(value.getText().toString()))) return true;
        }
        for (int i = 0; i < value.getChildCount() && remaining[0] > 0; i++) {
            if (node(value.getChild(i), seen, remaining)) return true;
        }
        return false;
    }
    private static boolean hidden(Object value) {
        if (value instanceof StatusBarNotification) return notification((StatusBarNotification) value);
        if (value instanceof AccessibilityEvent) return event((AccessibilityEvent) value);
        if (value instanceof AccessibilityNodeInfo) return node((AccessibilityNodeInfo) value);
        if (value instanceof AccessibilityWindowInfo) return node(((AccessibilityWindowInfo) value).getRoot());
        return false;
    }
    private static final XC_MethodHook CALLBACK = new XC_MethodHook() {
        @Override protected void beforeHookedMethod(MethodHookParam p) {
            if (!INTERNAL.get()) for (Object value : p.args) if (hidden(value)) { p.setResult(null); return; }
        }
    };
    private static void callbacks(Object service, String... names) {
        for (Class<?> type = service.getClass(); type != null; type = type.getSuperclass()) {
            for (Method method : type.getDeclaredMethods()) {
                if (Modifier.isAbstract(method.getModifiers())) continue;
                for (String name : names) if (name.equals(method.getName()) && CALLBACKS.add(method)) {
                    XposedBridge.hookMethod(method, CALLBACK);
                }
            }
        }
    }
    private static final XC_MethodHook RESULT = new XC_MethodHook() {
        @Override protected void afterHookedMethod(MethodHookParam p) {
            if (INTERNAL.get() || p.hasThrowable()) return;
            p.setResult(filter(p.getResult()));
        }
    };
    private static Object filter(Object value) {
        if (hidden(value)) return null;
        if (value instanceof List<?>) {
            List<Object> kept = new ArrayList<>();
            for (Object item : (List<?>) value) if (!hidden(item)) kept.add(item);
            return kept;
        }
        if (value instanceof StatusBarNotification[]) {
            List<Object> kept = new ArrayList<>();
            for (Object item : (Object[]) value) if (!hidden(item)) kept.add(item);
            return kept.toArray((Object[]) Array.newInstance(value.getClass().getComponentType(), kept.size()));
        }
        if (value instanceof android.util.SparseArray<?>) {
            android.util.SparseArray<Object> kept = new android.util.SparseArray<>();
            android.util.SparseArray<?> input = (android.util.SparseArray<?>) value;
            for (int i = 0; i < input.size(); i++) kept.put(input.keyAt(i), filter(input.valueAt(i)));
            return kept;
        }
        return value;
    }
    static void install(ClassLoader loader) {
        hook(ClipboardManager.class, "getPrimaryClip", new XC_MethodHook() {
            @Override protected void afterHookedMethod(MethodHookParam p) {
                if (!INTERNAL.get() && !p.hasThrowable() && clip((ClipData) p.getResult())) p.setResult(null);
            }
        });
        hook(ClipboardManager.class, "getPrimaryClipDescription", new XC_MethodHook() {
            @Override protected void afterHookedMethod(MethodHookParam p) {
                if (!INTERNAL.get() && !p.hasThrowable() && description((ClipDescription) p.getResult())) p.setResult(null);
            }
        });
        for (String method : new String[]{"hasPrimaryClip", "hasText", "reportPrimaryClipChanged"}) {
            hook(ClipboardManager.class, method, new XC_MethodHook() {
                @Override protected void beforeHookedMethod(MethodHookParam p) {
                    if (clipboardHidden((ClipboardManager) p.thisObject)) {
                        p.setResult("reportPrimaryClipChanged".equals(p.method.getName()) ? null : false);
                    }
                }
            });
        }
        XposedBridge.hookAllConstructors(NotificationListenerService.class, new XC_MethodHook() {
            @Override protected void afterHookedMethod(MethodHookParam p) {
                callbacks(p.thisObject, "onNotificationPosted", "onNotificationRemoved");
            }
        });
        for (String method : new String[]{"getActiveNotifications", "getSnoozedNotifications"}) {
            hook(NotificationListenerService.class, method, RESULT);
        }
        Class<?> ranking = optional("android.service.notification.NotificationListenerService$RankingMap", loader);
        hook(ranking, "getOrderedKeys", new XC_MethodHook() {
            @Override protected void afterHookedMethod(MethodHookParam p) {
                if (p.hasThrowable() || !(p.getResult() instanceof String[])) return;
                if (!INTERNAL.get()) {
                    INTERNAL.set(true);
                    try {
                        for (String key : (String[]) p.getResult()) {
                            Object item = XposedHelpers.callMethod(p.thisObject, "getRawRankingObject", key);
                            if (item instanceof NotificationListenerService.Ranking) {
                                android.app.NotificationChannel channel = ((NotificationListenerService.Ranking) item).getChannel();
                                String[] parts = key.split("\\|");
                                if (parts.length > 1 && source(parts[1]) && channel != null
                                    && (Rules.screenshot(channel.getId())
                                        || (channel.getName() != null && Rules.screenshot(channel.getName().toString())))) {
                                    HIDDEN_NOTIFICATION_KEYS.add(key);
                                }
                            }
                        }
                    } catch (Throwable ignored) {
                    } finally { INTERNAL.set(false); }
                }
                p.setResult(java.util.Arrays.stream((String[]) p.getResult())
                    .filter(key -> !HIDDEN_NOTIFICATION_KEYS.contains(key)).toArray(String[]::new));
            }
        });
        hook(ranking, "getRanking", new XC_MethodHook() {
            @Override protected void beforeHookedMethod(MethodHookParam p) {
                if (p.args.length > 0 && HIDDEN_NOTIFICATION_KEYS.contains(p.args[0])) p.setResult(false);
            }
        });
        hook(ranking, "getRawRankingObject", new XC_MethodHook() {
            @Override protected void beforeHookedMethod(MethodHookParam p) {
                if (!INTERNAL.get() && p.args.length > 0 && HIDDEN_NOTIFICATION_KEYS.contains(p.args[0])) p.setResult(null);
            }
        });
        XposedBridge.hookAllConstructors(AccessibilityService.class, new XC_MethodHook() {
            @Override protected void afterHookedMethod(MethodHookParam p) {
                callbacks(p.thisObject, "onAccessibilityEvent");
            }
        });
        for (String method : new String[]{"getRootInActiveWindow", "getWindows", "getWindowsOnAllDisplays", "findFocus"}) {
            hook(AccessibilityService.class, method, RESULT);
        }
        Class<?> client = optional("android.view.accessibility.AccessibilityInteractionClient", loader);
        for (String method : new String[]{"findAccessibilityNodeInfoByAccessibilityId",
            "findAccessibilityNodeInfosByViewId", "findAccessibilityNodeInfosByText", "findFocus",
            "focusSearch", "getRootInActiveWindow", "getWindow", "getWindows", "getWindowsOnAllDisplays"}) {
            hook(client, method, RESULT);
        }
    }
    private SignalHooks() {}
}
