package io.github.lwtdzh.appstateshield;

import org.matrix.vector.nativebridge.NativeAPI;
import java.util.HashSet;
import java.util.Set;

/** Register only libraries actually requested by the per-process policy. */
public final class NativeLibraries {
    private static final Set<String> registered = new HashSet<>();
    private static boolean prepared;
    private static native boolean prepare();
    private static native void finish();
    private NativeLibraries() {}

    public static synchronized void load(String name) {
        if (!registered.contains(name)) {
            if (!prepared) {
                System.loadLibrary("nativecompat");
                boolean active = prepare();
                try {
                    NativeAPI.recordNativeEntrypoint("lib" + name + ".so");
                    // native_init 在 loadLibrary 内执行；这里不能提前恢复 DobbyHook，
                    // 否则 libc 入口会回退到 Dobby 的 16 字节跳板。
                    System.loadLibrary(name);
                } finally {
                    if (active) finish();
                }
                prepared = true;
            } else {
                NativeAPI.recordNativeEntrypoint("lib" + name + ".so");
                System.loadLibrary(name);
            }
            registered.add(name);
        }
    }
}
