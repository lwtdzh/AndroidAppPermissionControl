package io.github.lwtdzh.appstateshield;

import android.content.Context;
import android.content.pm.*;
import android.os.Build;
import java.security.MessageDigest;
import java.util.*;

/** The marker is private to our verifier, not an API for arbitrary injected apps. */
final class VerifierIdentity {
    private static final Set<String> PACKAGES=Collections.unmodifiableSet(new HashSet<>(Arrays.asList(
        "io.github.lwtdzh.screenshotdetector",
        "io.github.lwtdzh.screenshotdetector.samplea",
        "io.github.lwtdzh.screenshotdetector.sampleb.screenshot")));
    private static final String CERTIFICATE="e5e7f749fd8d02ccb8b19439bf0ac56800801ab544ef2b8d0968cca036956dfe";
    static boolean trusted(Context context,String loadedPackage) {
        String pkg=context.getPackageName();
        if(!pkg.equals(loadedPackage)||!PACKAGES.contains(pkg))return false;
        // The verifier itself requires API 28. Older hosts have no authorized reader.
        if(Build.VERSION.SDK_INT<28)return false;
        try {
            PackageInfo info=context.getPackageManager().getPackageInfo(pkg,PackageManager.GET_SIGNING_CERTIFICATES);
            Signature[] signers=info.signingInfo==null?null:info.signingInfo.getApkContentsSigners();
            if(signers==null||signers.length!=1)return false;
            byte[] digest=MessageDigest.getInstance("SHA-256").digest(signers[0].toByteArray());
            StringBuilder hex=new StringBuilder();
            for(byte b:digest)hex.append(String.format(Locale.ROOT,"%02x",b&255));
            return CERTIFICATE.equals(hex.toString());
        } catch(Exception unavailable) { return false; }
    }
    private VerifierIdentity(){}
}
