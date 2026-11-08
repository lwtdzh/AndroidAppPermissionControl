package io.github.lwtdzh.screenshotprobe;

public final class ManifestReceiver extends android.content.BroadcastReceiver {
    public static int screenshots, ordinary;
    @Override public void onReceive(android.content.Context context, android.content.Intent intent) {
        if ("shieldprobe.MANIFEST_SCREENSHOT".equals(intent.getAction())) screenshots++;
        else ordinary++;
    }
}
