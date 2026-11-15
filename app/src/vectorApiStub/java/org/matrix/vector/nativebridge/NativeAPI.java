package org.matrix.vector.nativebridge;

/** Compile-only signature from Vector v2.2; implementation belongs to Vector. */
public final class NativeAPI {
    private NativeAPI() {}
    public static native void recordNativeEntrypoint(String libraryName);
}
