package com.android.id.impl;
import android.content.Context;
/** Debug-only named Xiaomi adapter fixture. Not a real OEM service. */
public final class IdProviderImpl {
    public String getOAID(Context c){return "fixture-xiaomi-oaid";}
    public String getVAID(Context c){return "fixture-xiaomi-vaid";}
    public String getAAID(Context c){return "fixture-xiaomi-aaid";}
    public String ordinary(){return "ordinary-xiaomi";}
}
