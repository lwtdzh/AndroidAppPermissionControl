package io.github.lwtdzh.screenshotdetector;

import android.app.Notification;
import android.content.ClipData;
import android.content.ClipDescription;
import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.provider.OpenableColumns;
import android.service.notification.StatusBarNotification;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import java.util.Locale;

/** Metadata predicates; values are never written to logs. */
final class Signals {
    static volatile Listener listener;
    interface Listener {
        void signal(Source source, String identity);
        void status(Source source, int message);
    }
    static void emit(Source source, String identity) {
        Listener current = listener;
        if (current != null) current.signal(source, identity);
    }
    static void status(Source source, int message) {
        Listener current = listener;
        if (current != null) current.status(source, message);
    }
    static boolean screenshot(CharSequence value) {
        if (value == null) return false;
        String lower = value.toString().toLowerCase(Locale.ROOT);
        for (String marker : new String[]{"screenshot", "screen_shot", "screen-shot", "screen shot",
            "screencap", "screen_capture", "screen-capture", "screen capture",
            "截图", "截屏", "螢幕截圖", "屏幕快照"})
            if (lower.contains(marker)) return true;
        return false;
    }
    static String simple(CharSequence value) {
        if (value == null) return "";
        String text = value.toString();
        return text.substring(Math.max(text.lastIndexOf('.'), text.lastIndexOf('/')) + 1);
    }
    static boolean screenshotFile(String path) {
        String lower = path.toLowerCase(Locale.ROOT);
        return screenshot(path) && (lower.endsWith(".png") || lower.endsWith(".jpg")
            || lower.endsWith(".jpeg") || lower.endsWith(".webp") || lower.endsWith(".heic"));
    }
    static boolean owner(CharSequence value) {
        if (value == null) return false;
        String name = value.toString().toLowerCase(Locale.ROOT);
        return name.equals("android") || name.equals("com.android.systemui")
            || name.equals("com.vivo.smartshot") || name.endsWith(".screenshot")
            || name.endsWith(".screencapture");
    }
    static boolean uri(Context context, Uri uri) {
        if (uri == null) return false;
        if (screenshot(uri.toString())) return true;
        try (Cursor cursor = context.getContentResolver().query(uri,
            new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            return cursor != null && cursor.moveToFirst() && screenshot(cursor.getString(0));
        } catch (RuntimeException ignored) { return false; }
    }
    static boolean clip(Context context, ClipData value) {
        if (value == null) return false;
        ClipDescription d = value.getDescription();
        if (d != null && d.hasMimeType("image/*") && screenshot(d.getLabel())) return true;
        for (int i = 0; i < value.getItemCount(); i++)
            if (uri(context, value.getItemAt(i).getUri())) return true;
        return false;
    }
    static boolean notification(StatusBarNotification sbn) {
        if (sbn == null || !owner(sbn.getPackageName())) return false;
        Notification n = sbn.getNotification();
        if (n == null) return false;
        if (screenshot(n.getChannelId())) return true;
        for (String key : new String[]{Notification.EXTRA_TITLE, Notification.EXTRA_TEXT,
            Notification.EXTRA_SUB_TEXT, Notification.EXTRA_BIG_TEXT, Notification.EXTRA_SUMMARY_TEXT})
            if (screenshot(n.extras.getCharSequence(key))) return true;
        CharSequence[] lines = n.extras.getCharSequenceArray(Notification.EXTRA_TEXT_LINES);
        if (lines != null) for (CharSequence line : lines) if (screenshot(line)) return true;
        return false;
    }
    static boolean event(AccessibilityEvent event) {
        if (!owner(event.getPackageName())) return false;
        if (screenshot(simple(event.getClassName())) || screenshot(event.getContentDescription())) return true;
        for (CharSequence text : event.getText()) if (screenshot(text)) return true;
        return false;
    }
    static boolean node(AccessibilityNodeInfo node, int[] budget) {
        if (node == null || budget[0]-- <= 0) return false;
        if (owner(node.getPackageName()) && (screenshot(simple(node.getClassName()))
            || screenshot(simple(node.getViewIdResourceName())) || screenshot(node.getText())
            || screenshot(node.getContentDescription()))) return true;
        for (int i = 0; i < node.getChildCount() && budget[0] > 0; i++)
            if (node(node.getChild(i), budget)) return true;
        return false;
    }
}
