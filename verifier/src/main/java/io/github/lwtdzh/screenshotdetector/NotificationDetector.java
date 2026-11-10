package io.github.lwtdzh.screenshotdetector;

import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;
import java.util.HashSet;
import java.util.Set;

public final class NotificationDetector extends NotificationListenerService {
    static volatile NotificationDetector live;
    static int deliveredScreenshot, deliveredOrdinary;
    private final Set<String> screenshotKeys = new HashSet<>();
    private final Set<String> baseline = new HashSet<>();
    void baseline() {
        baseline.clear();
        try {
            for (StatusBarNotification[] list : new StatusBarNotification[][]{
                getActiveNotifications(), getSnoozedNotifications()})
                if (list != null) for (StatusBarNotification n : list) if (Signals.notification(n)) {
                    screenshotKeys.add(n.getKey());
                    baseline.add(n.getKey() + ":" + n.getPostTime());
                }
        } catch (RuntimeException ignored) { }
    }
    @Override public void onListenerConnected() {
        live = this;
        Signals.status(Source.NOTIFICATION_EVENT, R.string.state_ready);
        Signals.status(Source.NOTIFICATION_LIST, R.string.state_ready);
        // Existing notifications are baselines, not new screenshot signals.
        baseline();
    }
    @Override public void onListenerDisconnected() {
        live = null;
        Signals.status(Source.NOTIFICATION_EVENT, R.string.state_notifications);
        Signals.status(Source.NOTIFICATION_LIST, R.string.state_notifications);
    }
    @Override public void onNotificationPosted(StatusBarNotification sbn) {
        if (Signals.notification(sbn)) deliveredScreenshot++;
        else deliveredOrdinary++;
        if (Signals.notification(sbn)) {
            screenshotKeys.add(sbn.getKey());
            emit(Source.NOTIFICATION_EVENT, sbn);
        }
    }
    @Override public void onNotificationRemoved(StatusBarNotification sbn) {
        if (screenshotKeys.contains(sbn.getKey()) || Signals.notification(sbn))
            emit(Source.NOTIFICATION_EVENT, sbn);
    }
    @Override public void onNotificationRankingUpdate(RankingMap ranking) {
        // Ranking contains keys, not screenshot metadata. Re-read actual notifications
        // for recognized keys rather than counting unrelated ranking changes as screenshots.
        if (Signals.listener != null && ranking.getOrderedKeys().length > 0) checkLists();
    }
    void checkLists() {
        try {
            for (StatusBarNotification[] list : new StatusBarNotification[][]{
                getActiveNotifications(), getSnoozedNotifications()}) {
                if (list != null) for (StatusBarNotification n : list) if (Signals.notification(n))
                    emit(Source.NOTIFICATION_LIST, n);
            }
        } catch (RuntimeException e) { Signals.status(Source.NOTIFICATION_LIST, R.string.state_permission); }
    }
    private void emit(Source source, StatusBarNotification n) {
        String identity = n.getKey() + ":" + n.getPostTime();
        if (!baseline.contains(identity)) Signals.emit(source, identity);
    }
    @Override public void onDestroy() { if (live == this) live = null; super.onDestroy(); }
}
