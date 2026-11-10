package io.github.lwtdzh.screenshotdetector;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;

public final class BroadcastDetector extends BroadcastReceiver {
    // Candidate actions, not a claim that each ROM emits them.
    static final String[] ACTIONS = {
        "android.intent.action.SCREENSHOT", "com.android.systemui.SCREENSHOT",
        "com.vivo.smartshot.SCREENSHOT", "com.vivo.smartshot.SCREENSHOT_FINISHED",
        "com.miui.screenshot", "com.oppo.intent.action.SCREENSHOT",
        "com.huawei.intent.action.SCREENSHOT", "io.github.lwtdzh.screenshotdetector.SCREENSHOT_TEST"
    };
    static IntentFilter filter() {
        IntentFilter filter = new IntentFilter();
        for (String action : ACTIONS) filter.addAction(action);
        return filter;
    }
    static void receive(Source source, Intent intent) {
        if (intent != null && Signals.screenshot(Signals.simple(intent.getAction())))
            Signals.emit(source, null);
    }
    @Override public void onReceive(Context context, Intent intent) { receive(Source.BROADCAST_MANIFEST, intent); }
}
