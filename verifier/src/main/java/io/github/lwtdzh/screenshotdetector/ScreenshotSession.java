package io.github.lwtdzh.screenshotdetector;

import java.io.Serializable;
import java.util.*;

/** Estimates screenshot events from independent signals; contains no Android UI state. */
final class ScreenshotSession implements Serializable {
    private static final long serialVersionUID = 1L;
    private static final long WINDOW_MS = 2000;
    private final LinkedHashMap<String, Event> identities = new LinkedHashMap<>();
    private final ArrayList<Event> recent = new ArrayList<>();
    private int count;
    private long lastWallTime;
    private static final class Event implements Serializable {
        private static final long serialVersionUID = 1L;
        final long time;
        final Set<String> sources = new HashSet<>();
        Event(long time, String source) { this.time = time; sources.add(source); }
    }
    int count() { return count; }
    long lastWallTime() { return lastWallTime; }
    void signal(String source, String identity, long now, long wallTime) {
        String key = null;
        if (identity != null) {
            // File routes share a pathname; MediaStore routes share a row ID.
            key = source.startsWith("MEDIA_") ? "media:" + identity :
                source.equals("FILE_OBSERVER") || source.equals("FILE_POLL") || source.startsWith("NATIVE_")
                    ? "file:" + identity : source + ":" + identity;
            Event known = identities.get(key);
            if (known != null) { known.sources.add(source); return; }
        }
        recent.removeIf(event -> now < event.time || now - event.time > WINDOW_MS);
        for (Event event : recent) {
            if (!event.sources.contains(source)) {
                event.sources.add(source);
                remember(key, event);
                return;
            }
        }
        // Anonymous UI/notification signals can repeat while the same overlay is visible.
        // Repeated official captures and distinct named files/rows still form new events.
        if (identity == null && !source.equals("OFFICIAL") && !recent.isEmpty()) return;
        Event event = new Event(now, source);
        recent.add(event);
        remember(key, event);
        count++;
        lastWallTime = wallTime;
    }
    private void remember(String key, Event event) {
        if (key == null) return;
        identities.put(key, event);
        if (identities.size() > 1024) identities.remove(identities.keySet().iterator().next());
    }
}
