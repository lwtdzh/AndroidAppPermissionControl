package io.github.lwtdzh.screenshotdetector;

import android.accessibilityservice.AccessibilityService;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;
import java.util.List;
import java.util.HashSet;
import java.util.Set;

public final class AccessibilityDetector extends AccessibilityService {
    static volatile AccessibilityDetector live;
    static int deliveredScreenshot, deliveredOrdinary;
    private boolean baselined;
    private final Set<Integer> knownWindows = new HashSet<>();
    @Override protected void onServiceConnected() {
        live = this;
        Signals.status(Source.ACCESSIBILITY_EVENT, R.string.state_ready);
        Signals.status(Source.ACCESSIBILITY_NODES, R.string.state_ready);
    }
    @Override public void onAccessibilityEvent(AccessibilityEvent event) {
        if (Signals.event(event)) deliveredScreenshot++;
        else deliveredOrdinary++;
        if (Signals.event(event)) Signals.emit(Source.ACCESSIBILITY_EVENT, null);
    }
    void checkNodes() {
        try {
            int[] budget = {256};
            Set<Integer> found = new HashSet<>();
            for (AccessibilityNodeInfo root : new AccessibilityNodeInfo[]{
                getRootInActiveWindow(), findFocus(AccessibilityNodeInfo.FOCUS_ACCESSIBILITY),
                findFocus(AccessibilityNodeInfo.FOCUS_INPUT)})
                if (Signals.node(root, budget)) found.add(root.getWindowId());
            List<AccessibilityWindowInfo> windows = getWindows();
            for (AccessibilityWindowInfo window : windows) {
                if (Signals.node(window.getRoot(), budget)) found.add(window.getId());
                if (budget[0] <= 0) break;
            }
            if (baselined) for (int window : found) if (!knownWindows.contains(window))
                Signals.emit(Source.ACCESSIBILITY_NODES, Integer.toString(window));
            knownWindows.clear(); knownWindows.addAll(found);
            baselined = true;
        } catch (RuntimeException e) { Signals.status(Source.ACCESSIBILITY_NODES, R.string.state_unsupported); }
    }
    void baseline() { baselined = false; knownWindows.clear(); checkNodes(); }
    @Override public void onInterrupt() { }
    @Override public void onDestroy() {
        if (live == this) live = null;
        Signals.status(Source.ACCESSIBILITY_EVENT, R.string.state_accessibility);
        Signals.status(Source.ACCESSIBILITY_NODES, R.string.state_accessibility);
        super.onDestroy();
    }
}
