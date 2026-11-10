package io.github.lwtdzh.appstateshield;

import android.content.Context;
import java.util.Locale;
import org.json.JSONObject;

/** Locale aliases and translations live in data, so adding a language needs no code change. */
final class UiText {
    private final JSONObject catalog;
    private final boolean simplified;
    UiText(Context context) {
        JSONObject selected = null;
        boolean zh = false;
        try (java.io.InputStream input = context.getAssets().open("settings-text.json")) {
            java.io.ByteArrayOutputStream bytes = new java.io.ByteArrayOutputStream();
            byte[] buffer = new byte[4096]; int n;
            while ((n = input.read(buffer)) != -1) bytes.write(buffer, 0, n);
            JSONObject data = new JSONObject(bytes.toString("UTF-8"));
            JSONObject aliases = data.getJSONObject("aliases"), locales = data.getJSONObject("locales");
            Locale locale = context.getResources().getConfiguration().getLocales().get(0);
            String key = locale.toLanguageTag();
            key = aliases.optString(key, key);
            selected = locales.optJSONObject(key);
            if (selected == null && !locale.getScript().isEmpty())
                selected = locales.optJSONObject(locale.getLanguage() + "-" + locale.getScript());
            if (selected == null) selected = locales.optJSONObject(aliases.optString(locale.getLanguage(), locale.getLanguage()));
            zh = key.equals("zh") || (selected != null && locale.getLanguage().equals("zh") && !key.contains("Hant"));
        } catch (Exception ignored) {}
        catalog = selected; simplified = zh;
    }
    String get(String zh, String en) {
        if (catalog != null && catalog.has(zh)) return catalog.optString(zh, en);
        return simplified ? zh : en;
    }
}
