package io.github.lwtdzh.appstateshield;

import android.content.*;
import android.database.Cursor;
import android.net.Uri;
import android.os.*;
import java.util.Arrays;

/** Exported read-only endpoint. A UID can request only packages belonging to it. */
public final class PolicyProvider extends ContentProvider {
    public static final String AUTHORITY = "io.github.lwtdzh.appstateshield.policy";
    @Override public boolean onCreate() { return true; }
    @Override public Bundle call(String method, String pkg, Bundle extras) {
        if (!"read".equals(method) || pkg == null) throw new SecurityException("Read only");
        String[] owned = getContext().getPackageManager().getPackagesForUid(Binder.getCallingUid());
        if (owned == null || !Arrays.asList(owned).contains(pkg))
            throw new SecurityException("Caller does not own package");
        PolicyStore store = new PolicyStore(getContext());
        Bundle result = new Bundle();
        result.putStringArray("disabled", store.disabled(pkg).toArray(new String[0]));
        result.putBoolean("custom", store.packages().contains(pkg));
        result.putInt("schema", 1);
        return result;
    }
    @Override public Cursor query(Uri u, String[] p, String s, String[] a, String o) { throw denied(); }
    @Override public Uri insert(Uri u, ContentValues v) { throw denied(); }
    @Override public int update(Uri u, ContentValues v, String s, String[] a) { throw denied(); }
    @Override public int delete(Uri u, String s, String[] a) { throw denied(); }
    @Override public String getType(Uri u) { return null; }
    private SecurityException denied() { return new SecurityException("Read only; use call(read, ownPackage)"); }
}
