package io.github.lwtdzh.appstateshield;

import android.app.*;
import android.content.pm.*;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.os.*;
import android.text.*;
import android.view.*;
import android.widget.*;
import java.util.*;
import java.util.concurrent.*;

/** Native, Vector-only settings. Editing is a draft until the user saves it. */
public final class SettingsActivity extends Activity {
    private PolicyStore store;
    private LinearLayout page, body, footer;
    private String screen = "home", selected, search = "";
    private boolean showSystem, loading;
    private Set<String> original = new LinkedHashSet<>(), draft = new LinkedHashSet<>();
    private final List<ApplicationInfo> apps = new ArrayList<>();
    private final ExecutorService loader = Executors.newSingleThreadExecutor();
    private final Map<String, Switch> switches = new HashMap<>();
    private UiText strings;
    private String t(String zh, String en) { return strings.get(zh, en); }
    private int dp(int n) { return Math.round(n * getResources().getDisplayMetrics().density); }
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        store = new PolicyStore(this);
        strings = new UiText(this);
        if (Build.VERSION.SDK_INT >= 33)
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT, this::back);
        if (saved != null) {
            screen = saved.getString("screen", "home"); selected = saved.getString("selected");
            search = saved.getString("search", ""); showSystem = saved.getBoolean("system");
            original = new LinkedHashSet<>(saved.getStringArrayList("original"));
            draft = new LinkedHashSet<>(saved.getStringArrayList("draft"));
        }
        render(); loadApps();
    }
    private void loadApps() {
        loading = true;
        loader.execute(() -> {
            List<ApplicationInfo> values = getPackageManager().getInstalledApplications(0);
            values.removeIf(a -> a.packageName.equals(getPackageName()));
            values.sort(Comparator.comparing(a -> label(a.packageName), String.CASE_INSENSITIVE_ORDER));
            runOnUiThread(() -> {
                if (isDestroyed()) return;
                apps.clear(); apps.addAll(values); loading = false;
                if ("picker".equals(screen)) renderPickerRows();
            });
        });
    }
    private String label(String pkg) {
        try { return getPackageManager().getApplicationLabel(getPackageManager().getApplicationInfo(pkg, 0)).toString(); }
        catch (PackageManager.NameNotFoundException e) { return pkg + t("（已卸载）", " (uninstalled)"); }
    }
    private LinearLayout column() {
        LinearLayout v = new LinearLayout(this); v.setOrientation(LinearLayout.VERTICAL); return v;
    }
    private TextView text(String value, int size, int color) {
        TextView v = new TextView(this); v.setText(value); v.setTextSize(size); v.setTextColor(color);
        v.setPadding(0, dp(4), 0, dp(4)); return v;
    }
    private TextView heading(String value) { return text(value, 22, 0xff182331); }
    private LinearLayout card() {
        LinearLayout v = column(); v.setPadding(dp(16), dp(12), dp(16), dp(12));
        GradientDrawable bg = new GradientDrawable(); bg.setColor(Color.WHITE); bg.setCornerRadius(dp(16));
        v.setBackground(bg);
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-1, -2);
        p.setMargins(0, dp(8), 0, dp(8)); body.addView(v, p); return v;
    }
    private Button button(String value, String id, Runnable action) {
        Button v = new Button(this); v.setText(value); v.setAllCaps(false); v.setContentDescription(id);
        if ("save".equals(id) || "add-app".equals(id)) {
            v.setBackgroundTintList(android.content.res.ColorStateList.valueOf(0xff175bc1));
            v.setTextColor(Color.WHITE);
        }
        if ("back".equals(id)) { v.setMinWidth(dp(44)); v.setMinimumWidth(dp(44)); }
        v.setOnClickListener(w -> action.run()); return v;
    }
    private void render() {
        page = column(); page.setBackgroundColor(0xfff2f4f8);
        page.setPadding(dp(20), 0, dp(20), 0);
        page.setOnApplyWindowInsetsListener((v, i) -> {
            if (Build.VERSION.SDK_INT >= 30 && v.getWindowInsetsController() != null)
                v.getWindowInsetsController().setSystemBarsAppearance(
                    WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS,
                    WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS);
            if (Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets b = i.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
                v.setPadding(dp(20) + b.left, b.top, dp(20) + b.right, b.bottom);
            } else v.setPadding(dp(20) + i.getSystemWindowInsetLeft(), i.getSystemWindowInsetTop(),
                dp(20) + i.getSystemWindowInsetRight(), i.getSystemWindowInsetBottom());
            return i;
        });
        LinearLayout bar = new LinearLayout(this); bar.setGravity(Gravity.CENTER_VERTICAL);
        if (!"home".equals(screen)) bar.addView(button("‹", "back", this::back));
        bar.addView(heading(t("应用状态屏蔽", "AppStateShield")), new LinearLayout.LayoutParams(0, -2, 1));
        page.addView(bar);
        body = column(); ScrollView scroll = new ScrollView(this); scroll.setFillViewport(true); scroll.addView(body);
        page.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        footer = column(); page.addView(footer);
        setContentView(page);
        if ("editor".equals(screen) && selected != null) renderEditor();
        else if ("picker".equals(screen)) renderPicker();
        else { screen = "home"; renderHome(); }
    }
    private void renderHome() {
        LinearLayout policy = card();
        policy.addView(text(t("默认全部开启", "All methods enabled by default"), 18, 0xff175bc1));
        policy.addView(text(t("Vector 作用域内，未定制的应用自动开启所有屏蔽方法，包括以后新增的方法。",
            "Every app in Vector scope uses all methods, including methods added in future versions."), 15, 0xff475569));
        policy.addView(text(t("请在 Vector 中选择作用域。此处的定制列表不会添加或移除作用域。",
            "Select scope in Vector. Custom settings do not change scope."), 13, 0xff667085));
        body.addView(heading(t("按应用定制", "App customizations")));
        body.addView(button(t("添加应用", "Add app"), "add-app", () -> { screen = "picker"; render(); }));
        List<String> packages = store.packages();
        if (packages.isEmpty()) body.addView(text(t("尚无定制应用。作用域内所有应用使用默认配置。",
            "No custom apps. All scoped apps use the defaults."), 15, 0xff667085));
        packages.sort(Comparator.comparing(this::label, String.CASE_INSENSITIVE_ORDER));
        for (String pkg : packages) {
            LinearLayout row = card(); row.setContentDescription("custom:" + pkg);
            row.addView(text(label(pkg), 18, 0xff182331));
            row.addView(text(pkg, 12, 0xff667085));
            long off = Arrays.stream(Methods.values()).filter(m -> store.disabled(pkg).contains(m.id)).count();
            row.addView(text(off == 0 ? t("全部开启", "All enabled") :
                t("已开启 ", "Enabled ") + (Methods.values().length - off) + "/" + Methods.values().length, 14, 0xff175bc1));
            row.setOnClickListener(v -> edit(pkg));
        }
        body.addView(text(BuildConfig.VERSION_NAME + " · Vector", 12, 0xff667085));
    }
    private LinearLayout pickerRows;
    private void renderPicker() {
        body.addView(heading(t("选择应用", "Choose app")));
        EditText input = new EditText(this); input.setSingleLine(true);
        input.setHint(t("搜索名称或包名", "Search name or package")); input.setContentDescription("app-search");
        input.setText(search); body.addView(input);
        Switch filter = new Switch(this); filter.setText(t("显示系统应用", "Show system apps"));
        filter.setContentDescription("show-system"); filter.setChecked(showSystem); body.addView(filter);
        filter.setOnCheckedChangeListener((v, checked) -> { showSystem = checked; renderPickerRows(); });
        pickerRows = column(); body.addView(pickerRows);
        input.addTextChangedListener(new TextWatcher() {
            public void beforeTextChanged(CharSequence s, int start, int count, int after) {}
            public void onTextChanged(CharSequence s, int start, int before, int count) { search = s.toString(); renderPickerRows(); }
            public void afterTextChanged(Editable e) {}
        });
        renderPickerRows();
    }
    private void renderPickerRows() {
        if (pickerRows == null || !"picker".equals(screen)) return;
        pickerRows.removeAllViews(); int count = 0;
        String query = search.toLowerCase(Locale.ROOT).trim();
        for (ApplicationInfo app : apps) {
            if (!showSystem && (app.flags & ApplicationInfo.FLAG_SYSTEM) != 0) continue;
            String title = label(app.packageName);
            if (!title.toLowerCase(Locale.ROOT).contains(query) && !app.packageName.toLowerCase(Locale.ROOT).contains(query)) continue;
            Button row = button(title + "\n" + app.packageName, "pick:" + app.packageName, () -> edit(app.packageName));
            row.setMinHeight(dp(64)); pickerRows.addView(row); count++;
        }
        if (count == 0) pickerRows.addView(text(loading ? t("正在读取应用…", "Loading apps…") :
            t("没有符合条件的应用", "No matching apps"), 15, 0xff667085));
    }
    private void edit(String pkg) {
        selected = pkg; original = store.disabled(pkg); draft = new LinkedHashSet<>(original);
        screen = "editor"; render();
    }
    private void renderEditor() {
        LinearLayout info = card(); info.addView(heading(label(selected)));
        info.addView(text(selected, 12, 0xff667085));
        info.addView(text(t("保存后，请强行停止并重新打开目标应用。", "After saving, force-stop and reopen the target app."), 14, 0xff475569));
        switches.clear();
        for (Methods method : Methods.values()) {
            LinearLayout row = card(); Switch toggle = new Switch(this);
            toggle.setText(t(method.zh, method.en)); toggle.setTextSize(17);
            toggle.setContentDescription("method:" + method.id);
            toggle.setChecked(!draft.contains(method.id)); switches.put(method.id, toggle);
            toggle.setOnCheckedChangeListener((v, enabled) -> {
                if (enabled) draft.remove(method.id); else draft.add(method.id);
            });
            row.addView(toggle); row.addView(text(t(method.detailZh, method.detailEn), 13, 0xff667085));
        }
        body.addView(button(t("全部开启", "Enable all"), "enable-all", () -> {
            for (Switch s : switches.values()) s.setChecked(true);
        }));
        body.addView(button(t("关闭已实现方法", "Disable implemented methods"), "disable-all", () -> {
            for (Switch s : switches.values()) s.setChecked(false);
        }));
        if (store.packages().contains(selected)) body.addView(button(t("删除定制，恢复默认", "Remove customization"), "remove-custom", () ->
            new AlertDialog.Builder(this).setTitle(t("恢复默认？", "Restore defaults?"))
                .setMessage(t("仅删除这个应用的定制，恢复所有方法开启。", "Remove only this app's customization and enable all methods."))
                .setNegativeButton(t("取消", "Cancel"), null)
                .setPositiveButton(t("恢复默认", "Restore"), (d, w) -> {
                    if (store.remove(selected)) home(); else failed();
                }).show()));
        LinearLayout actions = new LinearLayout(this);
        actions.addView(button(t("取消", "Cancel"), "cancel", this::back), new LinearLayout.LayoutParams(0, -2, 1));
        actions.addView(button(t("保存", "Save"), "save", () -> {
            if (store.save(selected, draft)) {
                Toast.makeText(this, t("已保存，重新启动目标应用后生效", "Saved. Restart the target app to apply."), Toast.LENGTH_LONG).show();
                home();
            } else failed();
        }), new LinearLayout.LayoutParams(0, -2, 1));
        footer.addView(actions);
    }
    private void failed() { Toast.makeText(this, t("保存失败，请重试", "Save failed. Please retry."), Toast.LENGTH_LONG).show(); }
    private void home() { screen = "home"; selected = null; render(); }
    private void back() {
        if ("editor".equals(screen) && !draft.equals(original)) {
            new AlertDialog.Builder(this).setTitle(t("修改尚未保存", "Unsaved changes"))
                .setMessage(t("离开将丢弃这些修改。", "Leaving will discard these changes."))
                .setNegativeButton(t("继续编辑", "Keep editing"), null)
                .setPositiveButton(t("丢弃", "Discard"), (d, w) -> home()).show();
        } else if ("home".equals(screen)) finish();
        else home();
    }
    @android.annotation.SuppressLint("GestureBackNavigation") // API 27–32 fallback; newer systems register above.
    @Override public void onBackPressed() { back(); }
    @Override protected void onSaveInstanceState(Bundle out) {
        out.putString("screen", screen); out.putString("selected", selected);
        out.putString("search", search); out.putBoolean("system", showSystem);
        out.putStringArrayList("draft", new ArrayList<>(draft)); out.putStringArrayList("original", new ArrayList<>(original));
        super.onSaveInstanceState(out);
    }
    @Override protected void onDestroy() { loader.shutdownNow(); super.onDestroy(); }
}
