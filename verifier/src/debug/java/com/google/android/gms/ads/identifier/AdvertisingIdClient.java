package com.google.android.gms.ads.identifier;
import android.content.Context;
/** Debug-only method shape. Production builds do not contain Google SDK fixtures. */
public final class AdvertisingIdClient {
    public static Info getAdvertisingIdInfo(Context c){return new Info();}
    public static final class Info {
        public String getId(){return "fixture-gaid";}
        public boolean isLimitAdTrackingEnabled(){return true;}
    }
}
