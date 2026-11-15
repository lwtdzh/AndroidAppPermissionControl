package com.bun.miitmdid.core;

/** Debug-only synchronous SDK delivery; no real OEM service is called. */
public final class MdidSdkHelper {
    public static int InitSdk(android.content.Context context, boolean log,
        com.bun.miitmdid.interfaces.IIdentifierListener listener) {
        listener.OnSupport(true, new io.github.lwtdzh.screenshotdetector.MachineFixtures.Supplier());
        return 0;
    }
}
