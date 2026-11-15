package io.github.lwtdzh.appstateshield;

import org.matrix.vector.nativebridge.NativeAPI;
import java.util.HashSet;
import java.util.Set;

/** Register only libraries actually requested by the per-process policy. */
public final class NativeLibraries {
    private static final Set<String> registered = new HashSet<>();
    private NativeLibraries() {}

    public static synchronized void load(String name) {
        if (!registered.contains(name)) {
            // Vector relocates this type descriptor with its own bridge on every boot.
            NativeAPI.recordNativeEntrypoint("lib" + name + ".so");
            registered.add(name);
        }
        System.loadLibrary(name);
    }
}
