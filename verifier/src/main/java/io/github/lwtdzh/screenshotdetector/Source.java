package io.github.lwtdzh.screenshotdetector;

enum Source {
    OFFICIAL, BINDER, MEDIA_OBSERVER, MEDIA_POLL, MEDIA_LEGACY, MEDIA_CLIENT,
    FILE_OBSERVER, FILE_POLL, NATIVE_INOTIFY, NATIVE_FILES, NATIVE_SYSCALL,
    BROADCAST_DYNAMIC, BROADCAST_MANIFEST, CLIPBOARD,
    NOTIFICATION_EVENT, NOTIFICATION_LIST, ACCESSIBILITY_EVENT, ACCESSIBILITY_NODES;

    String key() { return name().toLowerCase(java.util.Locale.ROOT); }
    int label(android.content.Context context) {
        return context.getResources().getIdentifier("source_" + key(), "string", context.getPackageName());
    }
}
