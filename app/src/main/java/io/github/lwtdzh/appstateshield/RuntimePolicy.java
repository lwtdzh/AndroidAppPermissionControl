package io.github.lwtdzh.appstateshield;

import java.util.*;
public final class RuntimePolicy {
    private static volatile Set<String> disabled = Collections.emptySet();
    static void set(String[] values) {
        disabled = values == null ? Collections.emptySet()
            : Collections.unmodifiableSet(new HashSet<>(Arrays.asList(values)));
    }
    public static boolean enabled(String id) { return !disabled.contains(id); }
    public static String[] enabledIds() {
        return Arrays.stream(Methods.values()).filter(m -> enabled(m.id)).map(m -> m.id).toArray(String[]::new);
    }
}
