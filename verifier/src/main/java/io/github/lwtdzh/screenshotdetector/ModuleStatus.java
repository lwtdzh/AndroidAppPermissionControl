package io.github.lwtdzh.screenshotdetector;

import android.os.Bundle;
/** Replaced by the module in scoped processes. An absent hook is explicit. */
public final class ModuleStatus {
    public static Bundle snapshot() {
        Bundle value = new Bundle(); value.putBoolean("injected", false);
        value.putStringArray("enabled", new String[0]); return value;
    }
}
