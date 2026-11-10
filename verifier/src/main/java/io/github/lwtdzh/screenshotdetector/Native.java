package io.github.lwtdzh.screenshotdetector;

import android.os.IBinder;

final class Native {
    static { System.loadLibrary("detector"); }
    static native IBinder activityTask();
    static native String[] files(String directory, boolean syscall);
    static native long watch(String[] directories);
    static native String[] events(long handle);
    static native void close(long handle);
    /** Capability mask: open, stat, read, pread, readv, mmap, fcntl, fstat, statx. */
    static native int descriptor(int fd);
}
