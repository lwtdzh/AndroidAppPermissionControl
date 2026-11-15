package io.github.lwtdzh.screenshotdetector;

import android.content.Context;
import android.location.*;
import android.os.*;
import android.telephony.*;
import android.telephony.gsm.GsmCellLocation;
import org.json.*;
import java.util.*;

/** Synthetic objects and explicit callback delivery, kept out of release APKs. */
public final class MachineFixtures {
    public static final class Supplier implements com.bun.miitmdid.interfaces.IdSupplier {
        public String getOAID(){return "fixture-msa-oaid";}
        public String getVAID(){return "fixture-msa-vaid";}
        public String getAAID(){return "fixture-msa-aaid";}
        public String ordinary(){return "ordinary-supplier";}
    }
    public static JSONObject read(Context c) throws Exception {
        JSONObject out=new JSONObject().put("kind","debug-only synthetic; not real OEM or modem");
        io.github.lwtdzh.deviceprofile.DeviceProfile valid=io.github.lwtdzh.deviceprofile.DeviceProfile.preset("xiaomi-14");
        if(!io.github.lwtdzh.deviceprofile.DeviceProfile.parse(valid.json()).values.equals(valid.values)
            || io.github.lwtdzh.deviceprofile.DeviceProfile.parse("{\"schema\":99,\"enabled\":true}").enabled
            || io.github.lwtdzh.deviceprofile.DeviceProfile.parse("{\"schema\":1,\"enabled\":true,\"values\":{\"imei\":\"123\"},\"selected\":[\"imei\"]}").enabled
            || io.github.lwtdzh.deviceprofile.DeviceProfile.off().get("imei")!=null
            || new io.github.lwtdzh.deviceprofile.DeviceProfile(true,1,"custom",valid.values,Collections.emptySet()).get("imei")!=null)
            throw new AssertionError("Device profile schema/whitelist failed");
        out.put("schemaControls",5);
        com.bun.miitmdid.core.MdidSdkHelper.InitSdk(c,false,(supported,s)->{
            try{out.put("msa",new JSONObject().put("oaid",s.getOAID()).put("vaid",s.getVAID())
                .put("aaid",s.getAAID()).put("ordinary",((Supplier)s).ordinary()).put("supportedControl",supported));}
            catch(JSONException error){throw new IllegalStateException(error);}
        });
        com.android.id.impl.IdProviderImpl x=new com.android.id.impl.IdProviderImpl();
        out.put("xiaomi",new JSONObject().put("oaid",x.getOAID(c)).put("vaid",x.getVAID(c)).put("aaid",x.getAAID(c)).put("ordinary",x.ordinary()));
        com.heytap.openid.IOpenID.Stub.Proxy proxy=new com.heytap.openid.IOpenID.Stub.Proxy();
        out.put("heytap",new JSONObject().put("oaid",proxy.getSerID(c.getPackageName(),"fixture","OUID"))
            .put("vaid",proxy.getSerID(c.getPackageName(),"fixture","DUID")).put("aaid",proxy.getSerID(c.getPackageName(),"fixture","AUID"))
            .put("ordinary",proxy.getSerID(c.getPackageName(),"fixture","OTHER")));
        Location raw=new Location("fixture");raw.setLatitude(10);raw.setLongitude(20);raw.setAccuracy(200);
        raw.setTime(123456);raw.setElapsedRealtimeNanos(789000);
        Bundle extras=new Bundle();extras.putString("fixture","ordinary-extra");raw.setExtras(extras);
        JSONObject callback=new JSONObject();
        LocationListener listener=new LocationListener(){
            @Override public void onLocationChanged(Location loc){
                try{callback.put("latitude",loc.getLatitude()).put("longitude",loc.getLongitude()).put("accuracy",loc.getAccuracy());}
                catch(JSONException ignored){}
            }
        };
        listener.onLocationChanged(raw);
        Parcel parcel=Parcel.obtain();Location copy;
        try{raw.writeToParcel(parcel,0);parcel.setDataPosition(0);copy=Location.CREATOR.createFromParcel(parcel);}
        finally{parcel.recycle();}
        out.put("location",new JSONObject().put("callback",callback).put("parcelLatitude",copy.getLatitude())
            .put("parcelLongitude",copy.getLongitude()).put("text",raw.toString()).put("timeControl",copy.getTime())
            .put("providerControl",copy.getProvider()).put("extras",raw.getExtras()==null?JSONObject.NULL:raw.getExtras().getString("fixture")));
        java.lang.reflect.Field lat=Location.class.getDeclaredField("mLatitudeDegrees"),lon=Location.class.getDeclaredField("mLongitudeDegrees");
        lat.setAccessible(true);lon.setAccessible(true);
        out.getJSONObject("location").put("serializedRawLatitude",lat.getDouble(copy)).put("serializedRawLongitude",lon.getDouble(copy));
        JSONObject nmea=new JSONObject();
        try{
            OnNmeaMessageListener receiver=(message,time)->{
                try{nmea.put("message",message).put("timestamp",time);}catch(JSONException ignored){}
            };
            Class<?> transport=Class.forName("android.location.LocationManager$GnssNmeaTransport");
            java.lang.reflect.Constructor<?> ctor=transport.getDeclaredConstructor(java.util.concurrent.Executor.class,Context.class,OnNmeaMessageListener.class);
            ctor.setAccessible(true);Object target=ctor.newInstance((java.util.concurrent.Executor)Runnable::run,c,receiver);
            transport.getMethod("onNmeaReceived",long.class,String.class).invoke(target,123L,
                "$GPGGA,123519,1000.0000,N,02000.0000,E,1,08,0.9,545.4,M,46.9,M,,*00");
        }catch(Exception error){
            nmea.put("error",error.toString());
            nmea.put("constructors",Arrays.toString(Class.forName("android.location.LocationManager$GnssNmeaTransport").getDeclaredConstructors()));
        }
        out.put("nmea",nmea);
        GsmCellLocation cell=new GsmCellLocation();cell.setLacAndCid(12,34);
        out.put("cell",new JSONObject().put("lac",cell.getLac()).put("cid",cell.getCid()));
        java.lang.reflect.Constructor<CellIdentityLte> identityCtor=CellIdentityLte.class.getDeclaredConstructor();
        identityCtor.setAccessible(true);CellIdentityLte identity=identityCtor.newInstance();
        java.lang.reflect.Field ci=CellIdentityLte.class.getDeclaredField("mCi");ci.setAccessible(true);ci.setInt(identity,35);
        Parcel cellParcel=Parcel.obtain();
        try{
            identity.writeToParcel(cellParcel,0);cellParcel.setDataPosition(0);CellIdentityLte cellCopy=CellIdentityLte.CREATOR.createFromParcel(cellParcel);
            out.getJSONObject("cell").put("lteText",identity.toString()).put("serializedRawCi",ci.getInt(cellCopy));
        }finally{cellParcel.recycle();}
        java.lang.reflect.Constructor<CellInfoLte> infoCtor=CellInfoLte.class.getDeclaredConstructor();infoCtor.setAccessible(true);
        CellSignalStrengthLte signal=infoCtor.newInstance().getCellSignalStrength();
        out.put("signal",new JSONObject().put("dbm",signal.getDbm()).put("level",signal.getLevel()));
        Parcel ordinary=Parcel.obtain();
        try{
            ordinary.writeString("ordinary-binder-string");ordinary.writeInt(42);ordinary.setDataPosition(0);
            out.put("parcelControl",ordinary.readString()).put("parcelIntControl",ordinary.readInt());
        }finally{ordinary.recycle();}
        return out;
    }
}
