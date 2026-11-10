package io.github.lwtdzh.screenshotshield;

import android.net.Uri;
import android.os.Build;
import java.util.Locale;

final class Rules {
    static final String[] MARKERS = {
        "screenshot", "screen_shot", "screen-shot", "screen shot",
        "screencap", "screen_capture", "screen-capture", "screen capture",
        "截屏", "截图", "螢幕截圖", "屏幕快照"
    };
    static boolean screenshot(String value) {
        if (value == null) return false;
        String lower = value.toLowerCase(Locale.ROOT);
        for (String marker : MARKERS) if (lower.contains(marker)) return true;
        return false;
    }
    static boolean file(String path) {
        if (path == null) return false;
        String absolute = new java.io.File(path).getAbsolutePath();
        boolean shared = absolute.startsWith("/storage/") || absolute.startsWith("/sdcard/")
            || absolute.startsWith("/mnt/media_rw/") || absolute.startsWith("/mnt/user/")
            || absolute.startsWith("/mnt/runtime/") || absolute.startsWith("/data/media/");
        return shared && screenshot(absolute);
    }
    static boolean media(Uri uri) {
        if (uri == null || !"content".equals(uri.getScheme())) return false;
        String authority = authority(uri);
        String path = uri.getPath();
        return ("media".equals(authority) || "media_legacy".equals(authority))
            && path != null && (path.contains("/images") || path.contains("/file"));
    }
    static boolean mediaRows(Uri uri) {
        return media(uri) && !uri.getPath().contains("/thumbnails");
    }
    static boolean mediaObserved(Uri uri) {
        if (!content(uri)) return false;
        String owner = authority(uri);
        return ("media".equals(owner) || "media_legacy".equals(owner))
            && (media(uri) || uri.getPathSegments().size() <= 1);
    }
    static boolean content(Uri uri) {
        return uri != null && "content".equals(uri.getScheme());
    }
    static boolean screenshotUri(Uri uri) {
        // Package/authority names may themselves contain "screenshot".
        return uri != null && screenshot(Uri.decode(uri.getEncodedPath()));
    }
    static boolean document(Uri uri) {
        if (uri == null || !"content".equals(uri.getScheme())) return false;
        String authority = authority(uri);
        return "com.android.externalstorage.documents".equals(authority)
            || "com.android.providers.media.documents".equals(authority);
    }
    static Uri documentImage(Uri uri) {
        if (uri == null || !"com.android.providers.media.documents".equals(authority(uri))) return null;
        String id = uri.getLastPathSegment();
        if (id != null && id.matches("image:[0-9]+")) {
            return Uri.parse("content://media/external/images/media/" + id.substring(6));
        }
        return null;
    }
    private static String authority(Uri uri) {
        String authority = uri.getAuthority();
        if (authority == null) return null;
        int userSeparator = authority.indexOf('@');
        return userSeparator > 0 && authority.substring(0, userSeparator).matches("[0-9]+")
            ? authority.substring(userSeparator + 1) : authority;
    }
    static boolean screenshotBroadcast(String action) {
        return action != null && screenshot(action.substring(action.lastIndexOf('.') + 1));
    }
    // Apply in the provider before limit/count, including projections without a filename.
    static String exclusion() {
        String[] columns = Build.VERSION.SDK_INT >= 29
            ? new String[]{"_display_name", "_data", "relative_path"}
            : new String[]{"_display_name", "_data"};
        StringBuilder sql = new StringBuilder();
        for (String column : columns) {
            for (String marker : MARKERS) {
                if (sql.length() != 0) sql.append(" AND ");
                // instr uses literal underscores rather than LIKE wildcard underscores.
                sql.append("instr(lower(coalesce(").append(column).append(",'')),'")
                    .append(marker.replace("'", "''")).append("')=0");
            }
        }
        return sql.toString();
    }
    static String combine(String selection) {
        return selection == null || selection.trim().isEmpty() ? exclusion()
            : "(" + selection + ") AND (" + exclusion() + ")";
    }
    private Rules() {}
}
