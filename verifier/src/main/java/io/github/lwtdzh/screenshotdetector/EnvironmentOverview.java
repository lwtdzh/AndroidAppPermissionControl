package io.github.lwtdzh.screenshotdetector;

import android.app.Activity;
import android.graphics.drawable.GradientDrawable;
import android.os.Handler;
import android.os.Looper;
import android.widget.*;
import org.json.JSONArray;
import org.json.JSONObject;
import java.text.SimpleDateFormat;
import java.util.*;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.Consumer;

/** One automatic read per entry, a manual refresh, and expandable selectable details. */
public final class EnvironmentOverview extends LinearLayout {
    private static final ExecutorService WORKER = Executors.newSingleThreadExecutor(r -> {
        Thread thread = new Thread(r, "environment-probe"); thread.setDaemon(true); return thread;
    });
    private final Activity activity;
    private final boolean zh;
    private final TextView summary;
    private final Button refresh, expand;
    private final LinearLayout details;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final Consumer<String> printer;
    private boolean active, busy, pending, expanded;
    private volatile boolean disposed;
    private int generation;
    public EnvironmentOverview(Activity activity, Consumer<String> printer) {
        super(activity); this.activity = activity; this.printer = printer;
        zh = getResources().getConfiguration().getLocales().get(0).getLanguage().equals("zh");
        setOrientation(VERTICAL); setPadding(dp(14), dp(10), dp(14), dp(10));
        GradientDrawable bg = new GradientDrawable(); bg.setColor(0xfff0f5ef); bg.setCornerRadius(dp(14)); setBackground(bg);
        addView(text(t("系统环境 · 打开后自动检查", "System environment · automatic check on entry"), 18));
        summary = text(t("等待检查…", "Waiting…"), 13);
        summary.setContentDescription("environment-summary"); addView(summary);
        addView(text(t("结果来自当前应用可见环境；无法确认会单独列出。", "Results describe this app's visible environment; unknown reads are listed separately."), 12));
        LinearLayout actions = new LinearLayout(activity);
        refresh = new Button(activity); refresh.setText(t("重新检查环境", "Check environment again"));
        refresh.setTextSize(12); refresh.setContentDescription("environment-refresh");
        refresh.setOnClickListener(v -> request()); actions.addView(refresh, new LayoutParams(0, -2, 1));
        expand = new Button(activity); expand.setText(t("展开检查详情", "Show check details"));
        expand.setTextSize(12); expand.setContentDescription("environment-details");
        details = new LinearLayout(activity); details.setOrientation(VERTICAL); details.setVisibility(GONE);
        expand.setOnClickListener(v -> {
            expanded = !expanded; details.setVisibility(expanded ? VISIBLE : GONE);
            expand.setText(expanded ? t("收起检查详情", "Hide check details") : t("展开检查详情", "Show check details"));
        }); actions.addView(expand, new LayoutParams(0, -2, 1)); addView(actions);
        addView(details);
    }
    private String t(String cn, String en) { return zh ? cn : en; }
    private int dp(int n) { return Math.round(n * getResources().getDisplayMetrics().density); }
    private TextView text(String value, int size) {
        TextView view = new TextView(getContext()); view.setText(value); view.setTextSize(size);
        view.setTextColor(0xff182331); view.setPadding(0, dp(3), 0, dp(3)); view.setTextIsSelectable(true); return view;
    }
    public void start() { if (active || disposed) return; active = true; generation++; request(); }
    public void stop() { active = false; pending = false; generation++; }
    public void dispose() { stop(); disposed = true; }
    private void request() {
        if (!active || disposed) return;
        if (busy) { pending = true; return; }
        busy = true; pending = false; refresh.setEnabled(false);
        summary.setText(t("正在检查环境与密钥证明…", "Checking environment and key attestation…"));
        int token = generation;
        // Hold only application context during potentially slow keystore work.
        android.content.Context context = activity.getApplicationContext();
        WORKER.execute(() -> {
            JSONObject result = disposed ? null : EnvironmentProbe.run(context);
            main.post(() -> {
                busy = false;
                if (disposed) return;
                refresh.setEnabled(true);
                if (active && token == generation && result != null) render(result);
                if (active && (pending || token != generation)) request();
            });
        });
    }
    private String status(String status) {
        switch (status) {
            case "PASS": return t("本项检查通过", "Check passed");
            case "WARN": return t("发现信号", "Signal found");
            case "UNKNOWN": return t("无法确认", "Unknown");
            default: return t("参考信息", "Information");
        }
    }
    private void render(JSONObject result) {
        JSONObject counts = result.optJSONObject("summary");
        if (counts == null) { summary.setText(t("检查未完成", "Check incomplete")); return; }
        String time = new SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(new Date(result.optLong("timestamp")));
        summary.setText(time + t(" · 通过 ", " · passed ") + counts.optInt("pass")
            + t(" · 信号 ", " · signals ") + counts.optInt("warn")
            + t(" · 未确认 ", " · unknown ") + counts.optInt("unknown")
            + t(" · 参考 ", " · info ") + counts.optInt("info"));
        details.removeAllViews();
        JSONArray checks = result.optJSONArray("checks");
        if (checks == null) return;
        for (int i = 0; i < checks.length(); i++) {
            JSONObject check = checks.optJSONObject(i); if (check == null) continue;
            String line = check.optString("label") + " · " + status(check.optString("status")) + "\n" + check.optString("value");
            TextView row = text(line + "\n" + check.optString("detail"), 12);
            row.setContentDescription("environment:" + check.optString("id"));
            if ("WARN".equals(check.optString("status"))) row.setTextColor(0xff9a4811);
            details.addView(row);
            if (printer != null) printer.accept(t("环境 · ", "Environment · ") + line.replace('\n', ' '));
        }
    }
}
