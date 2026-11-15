package io.github.lwtdzh.appstateshield;

import android.app.ActivityManager;
import android.bluetooth.BluetoothAdapter;
import android.content.*;
import android.content.res.Resources;
import android.database.Cursor;
import android.database.CursorWrapper;
import android.graphics.Point;
import android.hardware.SensorManager;
import android.location.Location;
import android.location.LocationManager;
import android.media.MediaDrm;
import android.net.Uri;
import android.net.wifi.*;
import android.os.*;
import android.provider.Settings;
import android.system.Os;
import android.telephony.*;
import android.telephony.gsm.GsmCellLocation;
import android.util.DisplayMetrics;
import android.util.Log;
import android.view.Display;
import de.robv.android.xposed.*;
import java.lang.reflect.*;
import java.net.NetworkInterface;
import java.util.*;
import java.io.File;
import io.github.lwtdzh.deviceprofile.CapacityView;
import io.github.lwtdzh.deviceprofile.TypedProperty;

/** Explicit typed API adapters. Every adapter checks the current field selection. */
final class DeviceHooks {
    private static final String TAG="DeviceProfile";
    private static ClassLoader loader;
    private static final Set<Class<?>> oemInstalled=Collections.newSetFromMap(new IdentityHashMap<>());
    private static final Set<Method> msaCallbacks=new HashSet<>();
    private static final Map<String,String> BUILD=new LinkedHashMap<>(), PROPERTIES=new LinkedHashMap<>();
    static {
        String[] fields={"BRAND","MANUFACTURER","MODEL","DEVICE","PRODUCT","BOARD","HARDWARE","FINGERPRINT","SERIAL",
            "VERSION:RELEASE","VERSION:INCREMENTAL"};
        String[] ids={"brand","manufacturer","model","device","product","board","hardware","fingerprint","serial","release","incremental"};
        for(int i=0;i<fields.length;i++)BUILD.put(fields[i],ids[i]);
        for(String field:new String[]{"ID","TYPE","TAGS"})BUILD.put(field,"fingerprint");
        for(String part:new String[]{"","system.","vendor.","product.","odm.","system_ext."})
            for(String id:new String[]{"brand","manufacturer","model","device","name"})
                PROPERTIES.put("ro.product."+part+id,id.equals("name")?"product":id);
        PROPERTIES.put("ro.product.name","product");
        for(String part:new String[]{"","system.","vendor.","product.","odm.","system_ext."}) {
            PROPERTIES.put("ro."+part+"build.fingerprint","fingerprint");
            for(String field:new String[]{"id","type","tags"})PROPERTIES.put("ro."+part+"build."+field,"fingerprint");
            PROPERTIES.put("ro."+part+"build.version.release","release");
            PROPERTIES.put("ro."+part+"build.version.incremental","incremental");
        }
        // DLKM images also publish build metadata. Use the selected fingerprint
        // for these reads; they are not independently verified OEM image data.
        for(String part:new String[]{"system_dlkm","vendor_dlkm","odm_dlkm"})
            for(String field:new String[]{"id","type","tags"})
                PROPERTIES.put("ro."+part+".build."+field,"fingerprint");
        PROPERTIES.put("ro.product.board","board");PROPERTIES.put("ro.hardware","hardware");
        PROPERTIES.put("ro.boot.hardware","hardware");PROPERTIES.put("ro.serialno","serial");
        PROPERTIES.put("ro.boot.serialno","serial");PROPERTIES.put("persist.sys.timezone","timezone");
        PROPERTIES.put("ro.sf.lcd_density","density");
    }
    static Map<String,String> buildFields(){return BUILD;}
    static Map<String,String> properties(){return PROPERTIES;}
    private static Class<?> optional(String name) { return XposedHelpers.findClassIfExists(name,loader); }
    private static void hook(Class<?> type,String method,XC_MethodHook callback) {
        if(type==null)return;
        try { DeviceRuntime.countHook(XposedBridge.hookAllMethods(type,method,callback).size()); }
        catch(Throwable e){Log.w(TAG,"API unavailable: "+type.getName()+"."+method);}
    }
    private static void string(Class<?> type,String method,String id) {
        hook(type,method,new XC_MethodHook(){
            @Override protected void beforeHookedMethod(MethodHookParam p){
                String v=DeviceRuntime.value(id);
                if(v!=null && ((Method)p.method).getReturnType()==String.class)p.setResult(v);
            }
        });
    }
    private static void integer(Class<?> type,String method,String id) {
        hook(type,method,new XC_MethodHook(){
            @Override protected void beforeHookedMethod(MethodHookParam p){
                String v=DeviceRuntime.value(id);if(v==null)return;
                Class<?> result=((Method)p.method).getReturnType();
                if(result==int.class)p.setResult(Integer.parseInt(v));
                else if(result==long.class)p.setResult(Long.parseLong(v));
            }
        });
    }
    static void install(ClassLoader cl) {
        loader=cl;
        telephony();identifiers();network();location();display();environment();
        AttestationHooks.install(cl);
        Class<?> props=optional("android.os.SystemProperties");
        hook(props,"get",new XC_MethodHook(){
            @Override protected void beforeHookedMethod(MethodHookParam p){
                if(p.args.length==0)return;
                String v=DeviceRuntime.property(String.valueOf(p.args[0]));
                if(v!=null)p.setResult(v);
            }
        });
        for(String name:new String[]{"getInt","getLong","getBoolean"})hook(props,name,new XC_MethodHook(){
            @Override protected void beforeHookedMethod(MethodHookParam p){
                if(p.args.length!=2)return;
                String v=DeviceRuntime.property(String.valueOf(p.args[0]));
                if(v==null)return;
                switch(p.method.getName()){
                    case "getInt":p.setResult(TypedProperty.integer(v,(Integer)p.args[1]));break;
                    case "getLong":p.setResult(TypedProperty.number(v,(Long)p.args[1]));break;
                    case "getBoolean":p.setResult(TypedProperty.bool(v,(Boolean)p.args[1]));break;
                }
            }
        });
        for(String name:OEM_NAMES)oem(optional(name));
        hook(ClassLoader.class,"loadClass",new XC_MethodHook(){
            @Override protected void afterHookedMethod(MethodHookParam p){
                if(!p.hasThrowable() && p.getResult() instanceof Class<?>) {
                    Class<?> type=(Class<?>)p.getResult();
                    if(OEM_NAMES.contains(type.getName()) || supplier(type))oem(type);
                }
            }
        });
    }
    private static void telephony(){
        noSim();
        presentSim();
        for(String method:new String[]{"getImei","getDeviceId"})hook(TelephonyManager.class,method,new XC_MethodHook(){
            @Override protected void beforeHookedMethod(MethodHookParam p) {
                int slot=p.args.length>0 && p.args[0] instanceof Integer?(Integer)p.args[0]:0;
                if(slot<0 || slot>1)return;
                String v=DeviceRuntime.value(slot==1?"imei2":"imei");
                if(v!=null)p.setResult(v);
            }
        });
        String[][] strings={{"getMeid","meid"},{"getSubscriberId","imsi"},{"getSimSerialNumber","iccid"},
            {"getLine1Number","phone"},{"getNetworkOperatorName","operator"},{"getSimOperatorName","operator"}};
        for(String[] e:strings)string(TelephonyManager.class,e[0],e[1]);
        string(Build.class,"getSerial","serial");string(SubscriptionInfo.class,"getIccId","iccid");
        string(SubscriptionInfo.class,"getNumber","phone");string(SubscriptionManager.class,"getPhoneNumber","phone");
        for(String method:new String[]{"getNetworkOperator","getSimOperator"})hook(TelephonyManager.class,method,new XC_MethodHook(){
            @Override protected void beforeHookedMethod(MethodHookParam p){
                String mcc=DeviceRuntime.value("mcc"),mnc=DeviceRuntime.value("mnc");
                // Both parts are selected: no real modem read is needed.
                if(mcc!=null && mnc!=null)p.setResult(mcc+mnc);
            }
            @Override protected void afterHookedMethod(MethodHookParam p){
                String mcc=DeviceRuntime.value("mcc"),mnc=DeviceRuntime.value("mnc");
                if(mcc==null && mnc==null)return;
                String raw=p.hasThrowable()?"":String.valueOf(p.getResult());
                if((mcc==null||mnc==null) && !raw.matches("\\d{5,6}"))return;
                p.setResult((mcc==null?raw.substring(0,3):mcc)+(mnc==null?raw.substring(3):mnc));
            }
        });
        string(SubscriptionInfo.class,"getMccString","mcc");string(SubscriptionInfo.class,"getMncString","mnc");
        integer(SubscriptionInfo.class,"getMcc","mcc");integer(SubscriptionInfo.class,"getMnc","mnc");
        integer(GsmCellLocation.class,"getLac","lac");integer(GsmCellLocation.class,"getCid","cid");
        hook(TelephonyManager.class,"getCellLocation",new XC_MethodHook(){
            @Override protected void beforeHookedMethod(MethodHookParam p){
                if(DeviceRuntime.value("lac")==null || DeviceRuntime.value("cid")==null)return;
                GsmCellLocation loc=new GsmCellLocation();
                loc.setLacAndCid(DeviceRuntime.number("lac",0),DeviceRuntime.number("cid",0));p.setResult(loc);
            }
        });
        for(String type:new String[]{"Gsm","Wcdma","Lte","Nr","Tdscdma","Cdma"}) {
            Class<?> identity=optional("android.telephony.CellIdentity"+type);
            for(String method:new String[]{"getMccString","getMncString"})
                string(identity,method,method.equals("getMccString")?"mcc":"mnc");
            for(String[] pair:new String[][]{{"getMcc","mcc"},{"getMnc","mnc"},{"getLac","lac"},
                {"getCid","cid"},{"getCi","cid"},{"getNci","cid"},{"getTac","tac"},{"getPci","pci"}})
                integer(identity,pair[0],pair[1]);
            cellObject(identity,new String[][]{{"mMccStr","mcc"},{"mMncStr","mnc"},{"mLac","lac"},
                {"mCid","cid"},{"mCi","cid"},{"mNci","cid"},{"mTac","tac"},{"mPci","pci"}});
            Class<?> signal=optional("android.telephony.CellSignalStrength"+type);
            integer(signal,"getDbm","signal");
            if(type.equals("Lte"))integer(signal,"getRsrp","signal");
            if(type.equals("Nr")) { integer(signal,"getSsRsrp","signal");integer(signal,"getCsiRsrp","signal"); }
            signalLevel(signal);
            cellObject(signal,new String[][]{{"mRssi","signal"},{"mRsrp","signal"},{"mCdmaDbm","signal"},
                {"mEvdoDbm","signal"},{"mCsiRsrp","signal"},{"mSsRsrp","signal"}});
        }
        integer(SignalStrength.class,"getDbm","signal");signalLevel(SignalStrength.class);
        hook(TelephonyManager.class,"getAllCellInfo",new XC_MethodHook(){
            @Override protected void beforeHookedMethod(MethodHookParam p) {
                // Full LTE selection uses a coherent synthetic object without querying the real modem.
                if(DeviceRuntime.value("cid")==null || DeviceRuntime.value("tac")==null
                    || DeviceRuntime.value("pci")==null || DeviceRuntime.value("mcc")==null || DeviceRuntime.value("mnc")==null)return;
                p.setResult(simulatedCells());
            }
        });
    }
    private static final int VIRTUAL_SUBSCRIPTION=1;
    private static boolean presentSlot(XC_MethodHook.MethodHookParam p){
        return p.args.length==0 || !(p.args[0] instanceof Integer) || (Integer)p.args[0]==0;
    }
    private static void simResult(Class<?> type,String method,java.util.function.Function<XC_MethodHook.MethodHookParam,Object> result){
        hook(type,method,new XC_MethodHook(){
            @Override protected void beforeHookedMethod(MethodHookParam p){
                if(DeviceRuntime.snapshot().simulatedSim())p.setResult(result.apply(p));
            }
        });
    }
    private static CellInfoLte simulatedCell(){
        CellInfoLte cell=(CellInfoLte)XposedHelpers.newInstance(CellInfoLte.class);
        CellIdentityLte identity=(CellIdentityLte)XposedHelpers.newInstance(CellIdentityLte.class);
        XposedHelpers.setObjectField(identity,"mMccStr",DeviceRuntime.value("mcc"));
        XposedHelpers.setObjectField(identity,"mMncStr",DeviceRuntime.value("mnc"));
        XposedHelpers.setObjectField(identity,"mAlphaLong",DeviceRuntime.value("operator"));
        XposedHelpers.setObjectField(identity,"mAlphaShort",DeviceRuntime.value("operator"));
        XposedHelpers.setIntField(identity,"mCi",DeviceRuntime.number("cid",1));
        XposedHelpers.setIntField(identity,"mTac",DeviceRuntime.number("tac",1));
        XposedHelpers.setIntField(identity,"mPci",DeviceRuntime.number("pci",1));
        XposedHelpers.setObjectField(cell,"mCellIdentityLte",identity);
        Object signal=XposedHelpers.newInstance(CellSignalStrengthLte.class);
        XposedHelpers.setIntField(signal,"mRsrp",DeviceRuntime.number("signal",-85));
        XposedHelpers.callMethod(signal,"updateLevel",new Object[]{null,null});
        XposedHelpers.setObjectField(cell,"mCellSignalStrengthLte",signal);
        XposedHelpers.callMethod(cell,"setRegistered",true);
        XposedHelpers.callMethod(cell,"setTimeStamp",SystemClock.elapsedRealtimeNanos());
        XposedHelpers.callMethod(cell,"setCellConnectionStatus",CellInfo.CONNECTION_PRIMARY_SERVING);
        return cell;
    }
    private static List<CellInfo> simulatedCells(){return Collections.singletonList(simulatedCell());}
    private static SubscriptionInfo simulatedSubscription(){
        Object builder=XposedHelpers.newInstance(optional("android.telephony.SubscriptionInfo$Builder"));
        XposedHelpers.callMethod(builder,"setId",VIRTUAL_SUBSCRIPTION);
        XposedHelpers.callMethod(builder,"setSimSlotIndex",0);
        XposedHelpers.callMethod(builder,"setIccId",DeviceRuntime.value("iccid"));
        XposedHelpers.callMethod(builder,"setCardString",DeviceRuntime.value("iccid"));
        XposedHelpers.callMethod(builder,"setDisplayName",DeviceRuntime.value("operator"));
        XposedHelpers.callMethod(builder,"setCarrierName",DeviceRuntime.value("operator"));
        XposedHelpers.callMethod(builder,"setNumber",DeviceRuntime.value("phone"));
        XposedHelpers.callMethod(builder,"setMcc",DeviceRuntime.value("mcc"));
        XposedHelpers.callMethod(builder,"setMnc",DeviceRuntime.value("mnc"));
        XposedHelpers.callMethod(builder,"setCountryIso",country());
        return (SubscriptionInfo)XposedHelpers.callMethod(builder,"build");
    }
    private static String country(){
        String mcc=DeviceRuntime.value("mcc");
        return "460".equals(mcc)?"cn":"454".equals(mcc)?"hk":"455".equals(mcc)?"mo":"466".equals(mcc)?"tw":"";
    }
    private static ServiceState simulatedService(){
        ServiceState state=new ServiceState();state.setState(ServiceState.STATE_IN_SERVICE);
        state.setOperatorName(DeviceRuntime.value("operator"),DeviceRuntime.value("operator"),
            DeviceRuntime.value("mcc")+DeviceRuntime.value("mnc"));
        state.setRoaming(false);
        XposedHelpers.callMethod(state,"setDataRegState",ServiceState.STATE_IN_SERVICE);
        for(int domain:new int[]{NetworkRegistrationInfo.DOMAIN_CS,NetworkRegistrationInfo.DOMAIN_PS}){
            Object builder=XposedHelpers.newInstance(optional("android.telephony.NetworkRegistrationInfo$Builder"));
            XposedHelpers.callMethod(builder,"setDomain",domain);
            XposedHelpers.callMethod(builder,"setTransportType",1);
            XposedHelpers.callMethod(builder,"setRegistrationState",1); // AOSP REGISTRATION_STATE_HOME (hidden SDK constant)
            XposedHelpers.callMethod(builder,"setAccessNetworkTechnology",TelephonyManager.NETWORK_TYPE_LTE);
            XposedHelpers.callMethod(builder,"setCellIdentity",simulatedCell().getCellIdentity());
            XposedHelpers.callMethod(builder,"setAvailableServices",domain==NetworkRegistrationInfo.DOMAIN_PS?
                Arrays.asList(NetworkRegistrationInfo.SERVICE_TYPE_DATA):
                Arrays.asList(NetworkRegistrationInfo.SERVICE_TYPE_VOICE,NetworkRegistrationInfo.SERVICE_TYPE_SMS));
            XposedHelpers.callMethod(state,"addNetworkRegistrationInfo",XposedHelpers.callMethod(builder,"build"));
        }
        return state;
    }
    private static void presentSim(){
        // One virtual physical SIM in slot 0; slot 1 has a modem ID but no card.
        simResult(TelephonyManager.class,"getSimState",p->presentSlot(p)?TelephonyManager.SIM_STATE_READY:TelephonyManager.SIM_STATE_ABSENT);
        simResult(TelephonyManager.class,"getSimCardState",p->presentSlot(p)?11:TelephonyManager.SIM_STATE_ABSENT); // SIM_STATE_PRESENT
        simResult(TelephonyManager.class,"getSimApplicationState",p->presentSlot(p)?10:TelephonyManager.SIM_STATE_UNKNOWN); // SIM_STATE_LOADED
        simResult(TelephonyManager.class,"hasIccCard",DeviceHooks::presentSlot);
        for(String method:new String[]{"getNetworkType","getDataNetworkType","getVoiceNetworkType"})
            simResult(TelephonyManager.class,method,p->TelephonyManager.NETWORK_TYPE_LTE);
        simResult(TelephonyManager.class,"getDataState",p->TelephonyManager.DATA_CONNECTED);
        for(String method:new String[]{"isDataEnabled","isDataConnectionAllowed"})
            simResult(TelephonyManager.class,method,p->true);
        simResult(TelephonyManager.class,"isNetworkRoaming",p->false);
        for(String method:new String[]{"getSimCountryIso","getNetworkCountryIso"})
            simResult(TelephonyManager.class,method,p->country());
        simResult(TelephonyManager.class,"getServiceState",p->simulatedService());
        simResult(TelephonyManager.class,"getSignalStrength",p->{
            SignalStrength signal=(SignalStrength)XposedHelpers.newInstance(SignalStrength.class);
            XposedHelpers.setObjectField(signal,"mLte",simulatedCell().getCellSignalStrength());return signal;
        });
        for(String method:new String[]{"getActiveSubscriptionInfoList","getAllSubscriptionInfoList",
            "getAvailableSubscriptionInfoList","getAccessibleSubscriptionInfoList"})
            simResult(SubscriptionManager.class,method,p->Collections.singletonList(simulatedSubscription()));
        simResult(SubscriptionManager.class,"getActiveSubscriptionInfo",p->
            (Integer)p.args[0]==VIRTUAL_SUBSCRIPTION?simulatedSubscription():null);
        simResult(SubscriptionManager.class,"getActiveSubscriptionInfoForSimSlotIndex",p->
            (Integer)p.args[0]==0?simulatedSubscription():null);
        simResult(SubscriptionManager.class,"getActiveSubscriptionInfoForIccIndex",p->
            Objects.equals(p.args[0],DeviceRuntime.value("iccid"))?simulatedSubscription():null);
        for(String method:new String[]{"getActiveSubscriptionInfoCount","getAllSubscriptionInfoCount"})
            simResult(SubscriptionManager.class,method,p->1);
        simResult(SubscriptionManager.class,"getActiveSubscriptionIdList",p->new int[]{VIRTUAL_SUBSCRIPTION});
        simResult(SubscriptionManager.class,"isActiveSubscriptionId",p->(Integer)p.args[0]==VIRTUAL_SUBSCRIPTION);
        simResult(SubscriptionManager.class,"getSlotIndex",p->(Integer)p.args[0]==VIRTUAL_SUBSCRIPTION?0:SubscriptionManager.INVALID_SIM_SLOT_INDEX);
        simResult(SubscriptionManager.class,"getSubscriptionIds",p->(Integer)p.args[0]==0?new int[]{VIRTUAL_SUBSCRIPTION}:new int[0]);
        simResult(SubscriptionManager.class,"getSubId",p->(Integer)p.args[0]==0?new int[]{VIRTUAL_SUBSCRIPTION}:new int[0]);
        for(String method:new String[]{"getDefaultSubscriptionId","getDefaultDataSubscriptionId",
            "getDefaultVoiceSubscriptionId","getDefaultSmsSubscriptionId"})
            simResult(SubscriptionManager.class,method,p->VIRTUAL_SUBSCRIPTION);
        simResult(TelephonyManager.class,"getSubscriptionId",p->VIRTUAL_SUBSCRIPTION);
        simResult(TelephonyManager.class,"getNetworkSpecifier",p->String.valueOf(VIRTUAL_SUBSCRIPTION));
    }
    private static void noSimResult(Class<?> type,String method,java.util.function.Supplier<Object> result){
        hook(type,method,new XC_MethodHook(){
            @Override protected void beforeHookedMethod(MethodHookParam p){
                if(DeviceRuntime.snapshot().noSim())p.setResult(result.get());
            }
        });
    }
    private static void noSim(){
        for(String method:new String[]{"getSimState","getSimCardState"})
            noSimResult(TelephonyManager.class,method,()->TelephonyManager.SIM_STATE_ABSENT);
        noSimResult(TelephonyManager.class,"getSimApplicationState",()->TelephonyManager.SIM_STATE_UNKNOWN);
        for(String method:new String[]{"hasIccCard","isDataEnabled","isDataConnectionAllowed","isNetworkRoaming"})
            noSimResult(TelephonyManager.class,method,()->false);
        for(String method:new String[]{"getNetworkOperator","getSimOperator","getNetworkOperatorName","getSimOperatorName",
            "getNetworkCountryIso","getSimCountryIso"})noSimResult(TelephonyManager.class,method,()->"");
        for(String method:new String[]{"getSubscriberId","getSimSerialNumber","getLine1Number","getGroupIdLevel1",
            "getIsimImpi","getIsimDomain","getIsimImpu","getCellLocation","getSignalStrength"})
            noSimResult(TelephonyManager.class,method,()->null);
        for(String method:new String[]{"getNetworkType","getDataNetworkType","getVoiceNetworkType"})
            noSimResult(TelephonyManager.class,method,()->TelephonyManager.NETWORK_TYPE_UNKNOWN);
        noSimResult(TelephonyManager.class,"getDataState",()->TelephonyManager.DATA_DISCONNECTED);
        noSimResult(TelephonyManager.class,"getServiceState",()->{
            android.telephony.ServiceState state=new android.telephony.ServiceState();state.setStateOutOfService();return state;
        });
        noSimResult(TelephonyManager.class,"getAllCellInfo",Collections::emptyList);
        noSimResult(TelephonyManager.class,"getNetworkSpecifier",()->"");
        noSimResult(TelephonyManager.class,"getSubscriptionId",()->SubscriptionManager.INVALID_SUBSCRIPTION_ID);
        noSimResult(SubscriptionManager.class,"getSlotIndex",()->SubscriptionManager.INVALID_SIM_SLOT_INDEX);
        for(String method:new String[]{"getSubscriptionIds","getSubId"})
            noSimResult(SubscriptionManager.class,method,()->new int[0]);
        for(String method:new String[]{"getActiveSubscriptionInfoList","getAllSubscriptionInfoList",
            "getAvailableSubscriptionInfoList","getAccessibleSubscriptionInfoList"})
            noSimResult(SubscriptionManager.class,method,Collections::emptyList);
        for(String method:new String[]{"getActiveSubscriptionInfo","getActiveSubscriptionInfoForSimSlotIndex",
            "getActiveSubscriptionInfoForIccIndex"})noSimResult(SubscriptionManager.class,method,()->null);
        for(String method:new String[]{"getActiveSubscriptionInfoCount","getAllSubscriptionInfoCount"})
            noSimResult(SubscriptionManager.class,method,()->0);
        noSimResult(SubscriptionManager.class,"getActiveSubscriptionIdList",()->new int[0]);
        noSimResult(SubscriptionManager.class,"isActiveSubscriptionId",()->false);
        for(String method:new String[]{"getDefaultSubscriptionId","getDefaultDataSubscriptionId",
            "getDefaultVoiceSubscriptionId","getDefaultSmsSubscriptionId"})
            noSimResult(SubscriptionManager.class,method,()->SubscriptionManager.INVALID_SUBSCRIPTION_ID);
        noSimResult(SubscriptionManager.class,"getPhoneNumber",()->"");
        for(String method:new String[]{"getIccId","getNumber","getCountryIso"})
            noSimResult(SubscriptionInfo.class,method,()->"");
        for(String method:new String[]{"getCarrierName","getDisplayName"})
            noSimResult(SubscriptionInfo.class,method,()->"");
        for(String method:new String[]{"getMcc","getMnc"})noSimResult(SubscriptionInfo.class,method,()->0);
        for(String method:new String[]{"getMccString","getMncString"})noSimResult(SubscriptionInfo.class,method,()->null);
        if(Build.VERSION.SDK_INT>=29)hook(TelephonyManager.class,"requestCellInfoUpdate",new XC_MethodHook(){
            @Override protected void beforeHookedMethod(MethodHookParam p){
                if(!DeviceRuntime.snapshot().noSim()&&!DeviceRuntime.snapshot().simulatedSim())return;
                java.util.concurrent.Executor executor=(java.util.concurrent.Executor)p.args[p.args.length-2];
                TelephonyManager.CellInfoCallback callback=(TelephonyManager.CellInfoCallback)p.args[p.args.length-1];
                List<CellInfo> cells=DeviceRuntime.snapshot().noSim()?Collections.emptyList():simulatedCells();
                executor.execute(()->callback.onCellInfo(cells));p.setResult(null);
            }
        });
    }
    private static void cellObject(Class<?> type,String[][] candidates) {
        if(type==null)return;
        Map<Field,String> fields=new LinkedHashMap<>();
        for(String[] pair:candidates)try {
            Field field=type.getDeclaredField(pair[0]);field.setAccessible(true);fields.put(field,pair[1]);
        }catch(NoSuchFieldException ignored){}
        for(String method:new String[]{"writeToParcel","toString"})hook(type,method,new XC_MethodHook(){
            @Override protected void beforeHookedMethod(MethodHookParam p)throws Throwable {
                if(fields.values().stream().noneMatch(id->DeviceRuntime.value(id)!=null))return;
                Object copy;
                try{copy=XposedHelpers.newInstance(type,p.thisObject);}catch(Throwable unavailable){return;}
                for(Map.Entry<Field,String> entry:fields.entrySet()){
                    String value=DeviceRuntime.value(entry.getValue());if(value==null)continue;
                    Field field=entry.getKey();
                    if(field.getType()==String.class)field.set(copy,value);
                    else if(field.getType()==long.class)field.setLong(copy,Long.parseLong(value));
                    else if(field.getType()==int.class)field.setInt(copy,Integer.parseInt(value));
                }
                p.setResult(XposedBridge.invokeOriginalMethod(p.method,copy,p.args));
            }
        });
    }
    private static void signalLevel(Class<?> type) {
        hook(type,"getLevel",new XC_MethodHook(){
            @Override protected void beforeHookedMethod(MethodHookParam p) {
                if(DeviceRuntime.value("signal")==null)return;
                int db=DeviceRuntime.number("signal",-85);p.setResult(db>=-90?4:db>=-100?3:db>=-110?2:db>=-120?1:0);
            }
        });
    }
    private static final Set<String> OEM_NAMES=new HashSet<>(Arrays.asList(
        "com.android.id.impl.IdProviderImpl","com.bun.miitmdid.supplier.IdSupplier",
        "com.bun.miitmdid.interfaces.IdSupplier","com.bun.miitmdid.core.MdidSdk",
        "com.bun.miitmdid.core.MdidSdkHelper",
        "com.heytap.openid.IOpenID$Stub$Proxy","com.zui.deviceidservice.IDeviceidInterface$Stub$Proxy",
        "com.samsung.android.deviceidservice.IDeviceIdService$Stub$Proxy",
        "com.google.android.gms.ads.identifier.AdvertisingIdClient$Info"));
    private static boolean supplier(Class<?> type) {
        if(type==null)return false;
        for(Class<?> iface:type.getInterfaces()) {
            String name=iface.getName();
            if(name.equals("com.bun.miitmdid.supplier.IdSupplier") ||
                name.equals("com.bun.miitmdid.interfaces.IdSupplier") ||
                name.equals("com.bun.supplier.IdSupplier") || supplier(iface))return true;
        }
        return supplier(type.getSuperclass());
    }
    private static synchronized void oem(Class<?> type) {
        if(type==null || type.isInterface() || !oemInstalled.add(type))return;
        if(type.getName().equals("com.bun.miitmdid.core.MdidSdkHelper")
            || type.getName().equals("com.bun.miitmdid.core.MdidSdk"))
            for(String name:new String[]{"InitSdk","initSdk"})hook(type,name,new XC_MethodHook(){
                @Override protected void beforeHookedMethod(MethodHookParam p) {
                    for(Object argument:p.args)if(argument!=null)msaListener(argument.getClass());
                }
            });
        // MSA returns concrete suppliers in callbacks. Abstract interface methods
        // have no executable entry; follow the declared interface metadata instead.
        if(supplier(type) && type.getSuperclass()!=Object.class)oem(type.getSuperclass());
        for(String[] pair:new String[][]{{"getOAID","oaid"},{"getVAID","vaid"},{"getAAID","aaid"},
            {"getOAIDForPackage","oaid"},{"getVAIDForPackage","vaid"},{"getAAIDForPackage","aaid"}})
            string(type,pair[0],pair[1]);
        if(type.getName().equals("com.google.android.gms.ads.identifier.AdvertisingIdClient$Info"))
            string(type,"getId","gaid");
        if(type.getName().equals("com.heytap.openid.IOpenID$Stub$Proxy"))hook(type,"getSerID",new XC_MethodHook(){
            @Override protected void beforeHookedMethod(MethodHookParam p) {
                if(p.args.length!=3)return;
                String id="OUID".equals(p.args[2])?"oaid":"DUID".equals(p.args[2])?"vaid":"AUID".equals(p.args[2])?"aaid":null;
                String v=DeviceRuntime.value(id);if(v!=null)p.setResult(v);
            }
        });
    }
    private static synchronized void msaListener(Class<?> type) {
        for(Class<?> current=type;current!=null && current!=Object.class;current=current.getSuperclass())
            for(Method method:current.getDeclaredMethods()) {
                boolean callback=false;
                for(Class<?> parameter:method.getParameterTypes()) {
                    String name=parameter.getName();
                    callback|=name.equals("com.bun.miitmdid.interfaces.IdSupplier")
                        || name.equals("com.bun.miitmdid.supplier.IdSupplier")
                        || name.equals("com.bun.supplier.IdSupplier");
                }
                if(!callback || method.getReturnType()!=void.class || !msaCallbacks.add(method))continue;
                try{DeviceRuntime.countHook(1);XposedBridge.hookMethod(method,new XC_MethodHook(){
                    @Override protected void beforeHookedMethod(MethodHookParam p) {
                        for(Object value:p.args)if(value!=null && supplier(value.getClass()))oem(value.getClass());
                    }
                });}catch(Throwable error){Log.w(TAG,"MSA callback unavailable: "+method.getName());}
            }
    }
    private static final ThreadLocal<Integer> queryDepth=ThreadLocal.withInitial(()->0);
    private static void identifiers(){
        for(String method:new String[]{"getString","getStringForUser"})hook(Settings.Secure.class,method,new XC_MethodHook(){
            @Override protected void beforeHookedMethod(MethodHookParam p){
                if(p.args.length>1 && Settings.Secure.ANDROID_ID.equals(p.args[1])) {
                    String v=DeviceRuntime.value("android_id");if(v!=null)p.setResult(v);
                }
            }
        });
        XC_MethodHook call=new XC_MethodHook(){
            @Override protected void afterHookedMethod(MethodHookParam p) {
                String value=DeviceRuntime.value("android_id");
                if(value==null || p.hasThrowable() || !(p.getResult() instanceof Bundle))return;
                boolean authority=false,method=false,key=false;
                for(Object arg:p.args) {
                    if(arg instanceof Uri)authority|="settings".equals(((Uri)arg).getAuthority());
                    if("settings".equals(arg))authority=true;
                    if("GET_secure".equals(arg))method=true;
                    if("android_id".equals(arg))key=true;
                }
                if(!authority && p.thisObject instanceof ContentProviderClient) {
                    try{authority="settings".equals(XposedHelpers.getObjectField(p.thisObject,"mAuthority"));}catch(Throwable ignored){}
                }
                if(authority&&method&&key) {
                    Bundle b=new Bundle((Bundle)p.getResult());b.putString("value",value);p.setResult(b);
                }
            }
        };
        for(Class<?> type:new Class<?>[]{ContentResolver.class,ContentProviderClient.class}) {
            hook(type,"call",call);
            hook(type,"query",new XC_MethodHook(){
                @Override protected void beforeHookedMethod(MethodHookParam p){
                    Uri uri=null;for(Object arg:p.args)if(arg instanceof Uri)uri=(Uri)arg;
                    String authority=uri==null?null:uri.getAuthority();
                    if(!"settings".equals(authority) && !"com.vivo.vms.IdProvider".equals(authority))return;
                    if("settings".equals(authority) && DeviceRuntime.value("android_id")==null)return;
                    if("com.vivo.vms.IdProvider".equals(authority) && DeviceRuntime.value("oaid")==null
                        && DeviceRuntime.value("vaid")==null && DeviceRuntime.value("aaid")==null)return;
                    int depth=queryDepth.get();queryDepth.set(depth+1);p.setObjectExtra("deviceDepth",depth);
                    if(depth>0)return;
                    p.setObjectExtra("deviceUri",uri);
                    // Keep row identification available even for a value-only projection.
                    Class<?>[] params=((Method)p.method).getParameterTypes();
                    for(int i=0;i<params.length;i++)if(params[i]==String[].class) {
                        String[] projection=(String[])p.args[i];p.setObjectExtra("deviceProjection",projection);
                        if("settings".equals(authority) && projection!=null && !Arrays.asList(projection).contains("name")) {
                            String[] extended=Arrays.copyOf(projection,projection.length+1);extended[projection.length]="name";p.args[i]=extended;
                        }break;
                    }
                }
                @Override protected void afterHookedMethod(MethodHookParam p){
                    Object depth=p.getObjectExtra("deviceDepth");if(depth!=null)queryDepth.set((Integer)depth);
                    Uri uri=(Uri)p.getObjectExtra("deviceUri");
                    if(uri==null || p.hasThrowable() || !(p.getResult() instanceof Cursor))return;
                    p.setResult(new IdCursor((Cursor)p.getResult(),uri,(String[])p.getObjectExtra("deviceProjection")));
                }
            });
        }
        hook(MediaDrm.class,"getPropertyByteArray",new XC_MethodHook(){
            @Override protected void beforeHookedMethod(MethodHookParam p){
                if(p.args.length==0 || !"deviceUniqueId".equals(p.args[0]))return;
                String v=DeviceRuntime.value("drm_id");if(v!=null)p.setResult(hex(v));
            }
        });
    }
    private static final class IdCursor extends CursorWrapper {
        private final Uri uri;private final int[] columns;private final String[] names;
        IdCursor(Cursor raw,Uri u,String[] requested){
            super(raw);uri=u;names=requested==null?raw.getColumnNames():requested.clone();columns=new int[names.length];
            for(int i=0;i<names.length;i++)columns[i]=raw.getColumnIndex(names[i]);
        }
        private int raw(int index){if(index<0||index>=columns.length)throw new IndexOutOfBoundsException();return columns[index];}
        private String replacement(int index){
            if(!"value".equals(names[index]))return null;
            if("settings".equals(uri.getAuthority())) {
                if(!uri.getPath().startsWith("/secure"))return null;
                int name=getWrappedCursor().getColumnIndex("name");
                String key=name>=0?getWrappedCursor().getString(name):uri.getLastPathSegment();
                return "android_id".equals(key)?DeviceRuntime.value("android_id"):null;
            }
            String path=uri.getPath();
            String id=path!=null && path.startsWith("/IdentifierId/OAID")?"oaid":
                path!=null && path.startsWith("/IdentifierId/VAID")?"vaid":
                path!=null && path.startsWith("/IdentifierId/AAID")?"aaid":null;
            return DeviceRuntime.value(id);
        }
        @Override public String[] getColumnNames(){return names.clone();}
        @Override public int getColumnCount(){return names.length;}
        @Override public String getColumnName(int i){return names[i];}
        @Override public int getColumnIndex(String name){for(int i=0;i<names.length;i++)if(names[i].equals(name))return i;return -1;}
        @Override public int getColumnIndexOrThrow(String n){int i=getColumnIndex(n);if(i<0)throw new IllegalArgumentException(n);return i;}
        @Override public String getString(int i){String v=replacement(i);return v==null?super.getString(raw(i)):v;}
        @Override public boolean isNull(int i){return replacement(i)==null && super.isNull(raw(i));}
        @Override public int getType(int i){return replacement(i)==null?super.getType(raw(i)):Cursor.FIELD_TYPE_STRING;}
        @Override public byte[] getBlob(int i){String v=replacement(i);return v==null?super.getBlob(raw(i)):v.getBytes(java.nio.charset.StandardCharsets.UTF_8);}
        @Override public short getShort(int i){String v=replacement(i);return v==null?super.getShort(raw(i)):number(v).shortValue();}
        @Override public int getInt(int i){String v=replacement(i);return v==null?super.getInt(raw(i)):number(v).intValue();}
        @Override public long getLong(int i){String v=replacement(i);return v==null?super.getLong(raw(i)):number(v).longValue();}
        @Override public float getFloat(int i){String v=replacement(i);return v==null?super.getFloat(raw(i)):number(v).floatValue();}
        @Override public double getDouble(int i){String v=replacement(i);return v==null?super.getDouble(raw(i)):number(v).doubleValue();}
        private Number number(String v){try{return Double.valueOf(v);}catch(NumberFormatException e){return 0;}}
        @Override public void copyStringToBuffer(int i,android.database.CharArrayBuffer b){
            String v=getString(i);if(v==null){b.sizeCopied=0;return;}if(b.data==null||b.data.length<v.length())b.data=new char[v.length()];
            v.getChars(0,v.length(),b.data,0);b.sizeCopied=v.length();
        }
    }
    static byte[] hex(String value) {
        byte[] bytes=new byte[value.length()/2];
        for(int i=0;i<bytes.length;i++)bytes[i]=(byte)Integer.parseInt(value.substring(i*2,i*2+2),16);return bytes;
    }
    private static void network(){
        string(WifiInfo.class,"getMacAddress","wifi_mac");string(WifiInfo.class,"getBSSID","bssid");
        hook(WifiInfo.class,"getSSID",new XC_MethodHook(){
            @Override protected void beforeHookedMethod(MethodHookParam p){
                String v=DeviceRuntime.value("ssid");if(v!=null)p.setResult("\""+v.replace("\"","")+"\"");
            }
        });
        string(BluetoothAdapter.class,"getAddress","bt_mac");
        hook(NetworkInterface.class,"getHardwareAddress",new XC_MethodHook(){
            @Override protected void beforeHookedMethod(MethodHookParam p){
                String name=((NetworkInterface)p.thisObject).getName(),v=DeviceRuntime.value("wifi_mac");
                if(v!=null && (name.startsWith("wlan")||name.startsWith("eth")))p.setResult(hex(v.replace(":","")));
            }
        });
        hook(WifiManager.class,"getScanResults",new XC_MethodHook(){
            @Override protected void afterHookedMethod(MethodHookParam p){
                if(p.hasThrowable() || !(p.getResult() instanceof List<?>))return;
                String ssid=DeviceRuntime.value("ssid"),bssid=DeviceRuntime.value("bssid");
                if(ssid==null&&bssid==null)return;
                List<ScanResult> result=new ArrayList<>();
                for(Object raw:(List<?>)p.getResult())if(raw instanceof ScanResult){
                    ScanResult copy;
                    if(Build.VERSION.SDK_INT>=30)copy=new ScanResult((ScanResult)raw);
                    else copy=(ScanResult)XposedHelpers.newInstance(ScanResult.class,raw);
                    if(ssid!=null)copy.SSID=ssid;if(bssid!=null)copy.BSSID=bssid;result.add(copy);
                }p.setResult(result);
            }
        });
    }
    private static void location(){
        for(String[] pair:new String[][]{{"getLatitude","latitude"},{"getLongitude","longitude"},{"getAccuracy","accuracy"}})
            hook(Location.class,pair[0],new XC_MethodHook(){
                @Override protected void beforeHookedMethod(MethodHookParam p){
                    String v=DeviceRuntime.value(pair[1]);if(v==null)return;
                    if(((Method)p.method).getReturnType()==float.class)p.setResult(Float.parseFloat(v));
                    else p.setResult(Double.parseDouble(v));
                }
            });
        hook(Location.class,"getExtras",new XC_MethodHook(){
            @Override protected void afterHookedMethod(MethodHookParam p){
                if(DeviceRuntime.value("latitude")!=null || DeviceRuntime.value("longitude")!=null)p.setResult(null);
            }
        });
        hook(Location.class,"writeToParcel",new XC_MethodHook(){
            @Override protected void beforeHookedMethod(MethodHookParam p)throws Throwable{
                if(DeviceRuntime.value("latitude")==null&&DeviceRuntime.value("longitude")==null&&DeviceRuntime.value("accuracy")==null)return;
                p.setResult(XposedBridge.invokeOriginalMethod(p.method,locationCopy((Location)p.thisObject),p.args));
            }
        });
        hook(Location.class,"toString",new XC_MethodHook(){
            @Override protected void beforeHookedMethod(MethodHookParam p)throws Throwable {
                if(DeviceRuntime.value("latitude")!=null||DeviceRuntime.value("longitude")!=null||DeviceRuntime.value("accuracy")!=null)
                    p.setResult(XposedBridge.invokeOriginalMethod(p.method,locationCopy((Location)p.thisObject),p.args));
            }
        });
        hook(LocationManager.class,"getLastKnownLocation",new XC_MethodHook(){
            @Override protected void afterHookedMethod(MethodHookParam p){
                if(DeviceRuntime.value("latitude")==null||DeviceRuntime.value("longitude")==null)return;
                if(!p.hasThrowable() && p.getResult() instanceof Location)return;
                Location synthetic=new Location(p.args.length>0?String.valueOf(p.args[0]):"gps");
                synthetic.setLatitude(DeviceRuntime.decimal("latitude",0));synthetic.setLongitude(DeviceRuntime.decimal("longitude",0));
                synthetic.setAccuracy((float)DeviceRuntime.decimal("accuracy",30));
                synthetic.setTime(System.currentTimeMillis());synthetic.setElapsedRealtimeNanos(SystemClock.elapsedRealtimeNanos());
                p.setResult(synthetic);
            }
        });
        // NMEA contains a second raw coordinate path. Transform only known coordinate sentences;
        // suppress other sentences while a coordinate is selected, rather than forward raw location.
        Class<?> transport=optional("android.location.LocationManager$GnssNmeaTransport");
        hook(transport,"onNmeaReceived",new XC_MethodHook(){
            @Override protected void beforeHookedMethod(MethodHookParam p) {
                if(DeviceRuntime.value("latitude")==null && DeviceRuntime.value("longitude")==null)return;
                for(int i=0;i<p.args.length;i++)if(p.args[i] instanceof String) {
                    String replacement=nmea((String)p.args[i]);
                    if(replacement==null){p.setResult(null);return;}p.args[i]=replacement;
                }
            }
        });
    }
    private static Location locationCopy(Location raw) {
        Location copy=new Location(raw);
        if(DeviceRuntime.value("latitude")!=null)copy.setLatitude(DeviceRuntime.decimal("latitude",0));
        if(DeviceRuntime.value("longitude")!=null)copy.setLongitude(DeviceRuntime.decimal("longitude",0));
        if(DeviceRuntime.value("accuracy")!=null)copy.setAccuracy((float)DeviceRuntime.decimal("accuracy",30));
        copy.setExtras(null);return copy;
    }
    private static String nmea(String raw){
        String line=raw.trim();int checksum=line.indexOf('*');if(checksum>=0)line=line.substring(0,checksum);
        String[] f=line.split(",",-1);if(f.length<7)return null;
        int lat,lon;
        if(f[0].endsWith("GGA")){lat=2;lon=4;}else if(f[0].endsWith("RMC") && f.length>7){lat=3;lon=5;}else return null;
        for(int index:new int[]{lat,lon}) {
            String id=index==lat?"latitude":"longitude",v=DeviceRuntime.value(id);if(v==null)continue;
            double coordinate=Double.parseDouble(v),absolute=Math.abs(coordinate);int degrees=(int)absolute;
            f[index]=String.format(Locale.US,index==lat?"%02d%07.4f":"%03d%07.4f",degrees,(absolute-degrees)*60);
            f[index+1]=index==lat?(coordinate<0?"S":"N"):(coordinate<0?"W":"E");
        }
        String result=String.join(",",f);int xor=0;for(int i=1;i<result.length();i++)xor^=result.charAt(i);
        return result+String.format(Locale.US,"*%02X\r\n",xor);
    }
    private static boolean displaySelected(){return DeviceRuntime.value("width")!=null||DeviceRuntime.value("height")!=null||DeviceRuntime.value("density")!=null;}
    private static boolean landscape(Object display) {
        if(display instanceof Display){int r=((Display)display).getRotation();return r==1||r==3;}
        return android.content.res.Resources.getSystem().getConfiguration().orientation==android.content.res.Configuration.ORIENTATION_LANDSCAPE;
    }
    private static void metrics(DisplayMetrics m,boolean wide){
        int width=m.widthPixels,height=m.heightPixels;
        m.widthPixels=DeviceRuntime.number(wide?"height":"width",width);
        m.heightPixels=DeviceRuntime.number(wide?"width":"height",height);
        if(DeviceRuntime.value("density")!=null){
            float old=m.density; m.densityDpi=DeviceRuntime.number("density",m.densityDpi);m.density=m.densityDpi/160f;
            m.scaledDensity=old==0?m.density:m.scaledDensity*m.density/old;
        }
    }
    private static void display(){
        for(String method:new String[]{"getMetrics","getRealMetrics"})hook(Display.class,method,new XC_MethodHook(){
            @Override protected void afterHookedMethod(MethodHookParam p){
                if(!p.hasThrowable()&&displaySelected()&&p.args.length>0 && p.args[0] instanceof DisplayMetrics)
                    metrics((DisplayMetrics)p.args[0],landscape(p.thisObject));
            }
        });
        for(String method:new String[]{"getSize","getRealSize"})hook(Display.class,method,new XC_MethodHook(){
            @Override protected void afterHookedMethod(MethodHookParam p){
                if(p.hasThrowable()||!displaySelected()||p.args.length==0||!(p.args[0] instanceof Point))return;
                Point point=(Point)p.args[0];boolean wide=landscape(p.thisObject);
                point.x=DeviceRuntime.number(wide?"height":"width",point.x);point.y=DeviceRuntime.number(wide?"width":"height",point.y);
            }
        });
        for(String method:new String[]{"getWidth","getHeight"})hook(Display.class,method,new XC_MethodHook(){
            @Override protected void afterHookedMethod(MethodHookParam p){
                if(p.hasThrowable())return;boolean width=p.method.getName().equals("getWidth")^landscape(p.thisObject);
                String v=DeviceRuntime.value(width?"width":"height");if(v!=null)p.setResult(Integer.parseInt(v));
            }
        });
        integer(Display.Mode.class,"getPhysicalWidth","width");integer(Display.Mode.class,"getPhysicalHeight","height");
        hook(Resources.class,"getDisplayMetrics",new XC_MethodHook(){
            @Override protected void afterHookedMethod(MethodHookParam p){
                if(p.hasThrowable()||!displaySelected()||!(p.getResult() instanceof DisplayMetrics))return;
                DisplayMetrics copy=new DisplayMetrics();copy.setTo((DisplayMetrics)p.getResult());
                metrics(copy,((Resources)p.thisObject).getConfiguration().orientation==2);p.setResult(copy);
            }
        });
    }
    private static void environment(){
        hook(ActivityManager.class,"getMemoryInfo",new XC_MethodHook(){
            @Override protected void afterHookedMethod(MethodHookParam p){
                String v=DeviceRuntime.value("total_ram");
                if(v!=null&&!p.hasThrowable()&&p.args[0] instanceof ActivityManager.MemoryInfo){
                    ActivityManager.MemoryInfo info=(ActivityManager.MemoryInfo)p.args[0];
                    long total=Long.parseLong(v)*(1L<<30);
                    info.availMem=CapacityView.remaining(info.availMem,info.totalMem,total);
                    info.threshold=CapacityView.remaining(info.threshold,info.totalMem,total);
                    info.totalMem=total;
                }
            }
        });
        storage();
        hook(TimeZone.class,"getDefault",new XC_MethodHook(){
            @Override protected void beforeHookedMethod(MethodHookParam p){
                String v=DeviceRuntime.value("timezone");if(v!=null)p.setResult(TimeZone.getTimeZone(v));
            }
        });
        hook(Locale.class,"getDefault",new XC_MethodHook(){
            @Override protected void beforeHookedMethod(MethodHookParam p){
                String v=DeviceRuntime.value("language");if(v!=null)p.setResult(Locale.forLanguageTag(v));
            }
        });
        hook(SensorManager.class,"getSensorList",new XC_MethodHook(){
            @Override protected void beforeHookedMethod(MethodHookParam p){
                if("true".equals(DeviceRuntime.value("hide_sensors")))p.setResult(Collections.emptyList());
            }
        });
        hook(SensorManager.class,"getDefaultSensor",new XC_MethodHook(){
            @Override protected void beforeHookedMethod(MethodHookParam p){
                if("true".equals(DeviceRuntime.value("hide_sensors")))p.setResult(null);
            }
        });
        hook(SensorManager.class,"registerListener",new XC_MethodHook(){
            @Override protected void beforeHookedMethod(MethodHookParam p){
                if("true".equals(DeviceRuntime.value("hide_sensors")) && ((Method)p.method).getReturnType()==boolean.class)p.setResult(false);
            }
        });
    }
    private static final Map<StatFs,Boolean> dataFilesystems=Collections.synchronizedMap(new WeakHashMap<>());
    private static long dataDevice=-1;
    private static boolean dataPath(String path) {
        try { return dataDevice!=-1&&Os.stat(path).st_dev==dataDevice; }
        catch(Exception unavailable){return false;}
    }
    private static long originalLong(Object object,String method) throws Throwable {
        return ((Number)XposedBridge.invokeOriginalMethod(object.getClass().getMethod(method),object,new Object[0])).longValue();
    }
    private static void storage(){
        try { dataDevice=Os.stat(Environment.getDataDirectory().getAbsolutePath()).st_dev; }
        catch(Exception unavailable){return;}
        XC_MethodHook remember=new XC_MethodHook(){
            @Override protected void afterHookedMethod(MethodHookParam p){
                if(!p.hasThrowable()&&p.args.length>0&&p.args[0] instanceof String)
                    dataFilesystems.put((StatFs)p.thisObject,dataPath((String)p.args[0]));
            }
        };
        try{DeviceRuntime.countHook(XposedBridge.hookAllConstructors(StatFs.class,remember).size());}
        catch(Throwable unavailable){Log.w(TAG,"StatFs constructors unavailable");}
        hook(StatFs.class,"restat",remember);
        for(String name:new String[]{"getTotalBytes","getBlockCount","getBlockCountLong",
            "getAvailableBytes","getFreeBytes","getAvailableBlocks","getAvailableBlocksLong","getFreeBlocks","getFreeBlocksLong"})
            hook(StatFs.class,name,new XC_MethodHook(){
                @Override protected void afterHookedMethod(MethodHookParam p) throws Throwable {
                    String v=DeviceRuntime.value("storage");
                    if(v==null||p.hasThrowable()||!Boolean.TRUE.equals(dataFilesystems.get(p.thisObject)))return;
                    long block=((StatFs)p.thisObject).getBlockSizeLong();
                    if(block<=0)return;
                    long count=CapacityView.total(Long.parseLong(v)*(1L<<30),block);
                    String method=p.method.getName();
                    boolean bytes=method.endsWith("Bytes");
                    long total=bytes?count*block:count;
                    long result=total;
                    if(!method.equals("getTotalBytes")&&!method.startsWith("getBlockCount")){
                        long original=originalLong(p.thisObject,"getBlockCountLong");
                        if(bytes)original*=block;
                        result=CapacityView.remaining(((Number)p.getResult()).longValue(),original,total);
                        if(bytes)result=result/block*block;
                    }
                    if(((Method)p.method).getReturnType()==int.class)p.setResult((int)Math.min(Integer.MAX_VALUE,result));
                    else p.setResult(result);
                }
            });
        for(String name:new String[]{"getTotalSpace","getFreeSpace","getUsableSpace"})hook(File.class,name,new XC_MethodHook(){
            @Override protected void afterHookedMethod(MethodHookParam p) throws Throwable {
                String v=DeviceRuntime.value("storage");
                if(v==null||p.hasThrowable()||!dataPath(((File)p.thisObject).getAbsolutePath()))return;
                long total=Long.parseLong(v)*(1L<<30);
                long result=p.method.getName().equals("getTotalSpace")?total:
                    CapacityView.remaining(((Number)p.getResult()).longValue(),originalLong(p.thisObject,"getTotalSpace"),total);
                p.setResult(result);
            }
        });
    }
}
