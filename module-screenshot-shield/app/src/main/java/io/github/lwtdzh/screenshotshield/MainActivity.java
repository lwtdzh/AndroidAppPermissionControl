package io.github.lwtdzh.screenshotshield;

import android.app.Activity;
import android.os.Bundle;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/** Informational only: Vector owns module enablement and application scope. */
public final class MainActivity extends Activity {
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        int space = Math.round(24 * getResources().getDisplayMetrics().density);
        layout.setPadding(space, space * 2, space, space);
        add(layout, R.string.app_name, 28);
        add(layout, R.string.status_enabled, 18);
        add(layout, R.string.setup_instructions, 16);
        add(layout, R.string.coverage_summary, 16);
        add(layout, R.string.visibility_notice, 16);
        add(layout, R.string.scope_notice, 16);
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.addView(layout, new ScrollView.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        setContentView(scroll);
    }
    private void add(LinearLayout layout, int text, int size) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextSize(size);
        view.setPadding(0, 0, 0, Math.round(20 * getResources().getDisplayMetrics().density));
        layout.addView(view);
    }
}
