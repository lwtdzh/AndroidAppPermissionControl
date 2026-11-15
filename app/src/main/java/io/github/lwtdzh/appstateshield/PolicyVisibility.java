package io.github.lwtdzh.appstateshield;

import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.util.Log;
import java.util.Set;
import java.util.TreeSet;

/** A read URI grant makes the provider visible without changing UID authorization. */
final class PolicyVisibility {
    static void grant(Context context, String pkg) {
        try {
            context.grantUriPermission(pkg, Uri.parse("content://" + PolicyProvider.AUTHORITY),
                Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_PREFIX_URI_PERMISSION);
        } catch (IllegalArgumentException error) {
            // A saved package can have been uninstalled.
            Log.w("AppStateShield", "Policy visibility unavailable for saved package");
        }
    }
    static void restore(Context context) {
        Set<String> packages = new TreeSet<>(new PolicyStore(context).packages());
        packages.addAll(new DeviceStore(context).packages());
        for (String pkg : packages) grant(context, pkg);
    }
}
