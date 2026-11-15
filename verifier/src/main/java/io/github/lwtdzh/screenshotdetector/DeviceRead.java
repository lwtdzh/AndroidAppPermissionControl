package io.github.lwtdzh.screenshotdetector;

import android.app.ActivityManager;
import android.bluetooth.BluetoothAdapter;
import android.content.*;
import android.database.Cursor;
import android.graphics.Point;
import android.hardware.Sensor;
import android.hardware.SensorManager;
import android.location.*;
import android.media.MediaDrm;
import android.net.Uri;
import android.net.wifi.*;
import android.os.*;
import android.provider.Settings;
import android.util.DisplayMetrics;
import android.view.*;
import org.json.*;
import java.net.NetworkInterface;
import java.util.*;
import java.util.concurrent.*;

/** Ordinary API reads only. Profile configuration is never used as observed data. */
public final class DeviceRead {
    public interface Read { Object get() throws Exception; }
    private static boolean nativeLoaded;
    private static native String nativeSnapshot();
    private static final ExecutorService OTHER=pool(8);
    private static final Map<String,Pending> pending=new HashMap<>();
    private static final ThreadLocal<Long> sampleDeadline=new ThreadLocal<>();
    private static ExecutorService pool(int max) {
        return new ThreadPoolExecutor(0,max,30,TimeUnit.SECONDS,new SynchronousQueue<>(),
            r->{Thread thread=new Thread(r,"DeviceApiRead");thread.setDaemon(true);return thread;});
    }
    private static final class Pending {
        final long revision;final Future<Object> result;
        Pending(long rev,Future<Object> value){revision=rev;result=value;}
    }
    private static Object bounded(String id,String source,Read action) throws Exception {
        long revision=ModuleStatus.snapshot().getLong("deviceRevision");
        Pending read;
        synchronized(pending){
            read=pending.get(id);
            if(read==null || read.result.isDone() || read.revision!=revision) {
                if(read!=null&&!read.result.isDone())read.result.cancel(true);
                read=new Pending(revision,OTHER.submit(action::get));pending.put(id,read);
            }
        }
        // Reuse stalled non-phone reads; Binder may ignore interruption.
        Long deadline=sampleDeadline.get();
        long remaining=deadline==null?80:Math.max(0,TimeUnit.NANOSECONDS.toMillis(deadline-System.nanoTime()));
        return read.result.get(Math.min(80,remaining),TimeUnit.MILLISECONDS);
    }
    private static void put(JSONObject out,String id,String source,Read action) {
        JSONObject row=new JSONObject();
        try { Object value=bounded(id,source,action);row.put("value",value==null?JSONObject.NULL:value); }
        catch(Throwable error){
            Throwable cause=error;
            while((cause instanceof java.lang.reflect.InvocationTargetException || cause instanceof ExecutionException)
                && cause.getCause()!=null)cause=cause.getCause();
            try { row.put("error",cause.getClass().getSimpleName()).put("detail",cause.getMessage()); }catch(JSONException ignored){}
        }
        try { row.put("source",source);out.put(id,row); }catch(JSONException ignored){}
    }
    private static Object property(String key) throws Exception {
        return Class.forName("android.os.SystemProperties").getMethod("get",String.class).invoke(null,key);
    }
    private static Object settingsQuery(Context c) {
        try(Cursor cursor=c.getContentResolver().query(Settings.Secure.CONTENT_URI,
            new String[]{"value"},"name=?",new String[]{"android_id"},null)){
            return cursor!=null && cursor.moveToFirst()?cursor.getString(0):null;
        }
    }
    private static Object vivo(Context c,String id) {
        try(Cursor cursor=c.getContentResolver().query(Uri.parse("content://com.vivo.vms.IdProvider/IdentifierId/"+id),
            null,null,null,null)){
            return cursor!=null&&cursor.moveToFirst()?cursor.getString(cursor.getColumnIndexOrThrow("value")):null;
        }
    }
    private static Object xiaomi(Context c,String method) throws Exception {
        Class<?> provider=Class.forName("com.android.id.impl.IdProviderImpl");
        return provider.getMethod(method,Context.class).invoke(provider.getDeclaredConstructor().newInstance(),c);
    }
    @SuppressWarnings({"deprecation","MissingPermission"})
    public static JSONObject read(Context c,Display display) {
        // A complete sample must leave time for the next two-second tick, even
        // when many Binder services fail at once. Pending tasks finish separately.
        sampleDeadline.set(System.nanoTime()+TimeUnit.MILLISECONDS.toNanos(1700));
        JSONObject result=new JSONObject(),rows=new JSONObject();
        try {
            result.put("timestamp",System.currentTimeMillis()).put("elapsed",SystemClock.elapsedRealtime())
                .put("pid",android.os.Process.myPid()).put("package",c.getPackageName());
            Bundle marker=ModuleStatus.snapshot();JSONObject module=new JSONObject();
            for(String key:marker.keySet()) {
                Object value=marker.get(key);
                module.put(key,value instanceof String[]?new JSONArray(Arrays.asList((String[])value)):value);
            }
            result.put("module",module).put("early",LifecycleProbe.snapshot());
        }catch(JSONException ignored){}
        put(rows,"brand","Build.BRAND",()->Build.BRAND);put(rows,"manufacturer","Build.MANUFACTURER",()->Build.MANUFACTURER);
        put(rows,"model","Build.MODEL",()->Build.MODEL);put(rows,"device","Build.DEVICE",()->Build.DEVICE);
        put(rows,"product","Build.PRODUCT",()->Build.PRODUCT);put(rows,"board","Build.BOARD",()->Build.BOARD);
        put(rows,"hardware","Build.HARDWARE",()->Build.HARDWARE);put(rows,"fingerprint","Build.FINGERPRINT",()->Build.FINGERPRINT);
        put(rows,"release","Build.VERSION.RELEASE",()->Build.VERSION.RELEASE);
        put(rows,"incremental","Build.VERSION.INCREMENTAL",()->Build.VERSION.INCREMENTAL);
        put(rows,"build_metadata","Build.ID / TYPE / TAGS / SDK_INT",()->new JSONObject()
            .put("id",Build.ID).put("type",Build.TYPE).put("tags",Build.TAGS).put("sdk",Build.VERSION.SDK_INT));
        put(rows,"serial","Build.getSerial",Build::getSerial);put(rows,"serial_static","Build.SERIAL",()->Build.SERIAL);
        put(rows,"android_id","Settings.Secure.getString",()->Settings.Secure.getString(c.getContentResolver(),"android_id"));
        put(rows,"android_id_cursor","settings secure value-only cursor",()->settingsQuery(c));
        put(rows,"oaid","vivo IdProvider query",()->vivo(c,"OAID"));
        put(rows,"vaid","vivo IdProvider query",()->vivo(c,"VAID"));
        put(rows,"aaid","vivo IdProvider query",()->vivo(c,"AAID"));
        put(rows,"xiaomi_oaid","Xiaomi IdProviderImpl.getOAID",()->xiaomi(c,"getOAID"));
        put(rows,"gaid","Google AdvertisingIdClient (if SDK is present)",()->{
            Class<?> client=Class.forName("com.google.android.gms.ads.identifier.AdvertisingIdClient");
            Object info=client.getMethod("getAdvertisingIdInfo",Context.class).invoke(null,c);
            return info.getClass().getMethod("getId").invoke(info);
        });
        // Discard stalled Binder calls with the phone worker, keeping this
        // Activity process alive. These are still real APIs under the same UID.
        Map<String,String> phoneSources=new LinkedHashMap<>();
        String[] ids={"imei","imei2","device_id","meid","imsi","iccid","phone","operator","mcc","mnc","lac","cid",
            "tac","pci","lte_ci","lte_mcc","lte_mnc","signal"};
        String[] sources={"getImei(0)","getImei(1)","getDeviceId","getMeid","getSubscriberId","getSimSerialNumber",
            "getLine1Number","getNetworkOperatorName","getNetworkOperator / MCC","getNetworkOperator / MNC",
            "getCellLocation.getLac","getCellLocation.getCid","getAllCellInfo / LTE","getAllCellInfo / LTE",
            "getAllCellInfo / LTE","getAllCellInfo / LTE","getAllCellInfo / LTE","getAllCellInfo / LTE"};
        for(int i=0;i<ids.length;i++)phoneSources.put(ids[i],"TelephonyManager."+sources[i]+" (same-UID phone worker)");
        for(String id:new String[]{"sim_state","sim_state_slot0","sim_state_slot1","sim_card_state","sim_application_state",
            "has_sim","sim_operator","sim_operator_name","sim_country","network_country","network_type","voice_network_type",
            "data_state","roaming","subscription_count","default_subscription","subscriptions","service_state","cells","async_cells"})
            phoneSources.put(id,"Android telephony / subscription API · "+id+" (same-UID phone worker)");
        try {
            JSONObject phone=PhoneReadService.read(c);
            if(phone.optLong("revision")!=ModuleStatus.snapshot().getLong("deviceRevision"))
                throw new IllegalStateException("Phone worker profile changed during sample");
            result.put("phoneWorker",phone);
            JSONObject observed=phone.getJSONObject("reads");
            for(Map.Entry<String,String> entry:phoneSources.entrySet())
                rows.put(entry.getKey(),observed.getJSONObject(entry.getKey()).put("source",entry.getValue()));
        }catch(Exception error){
            for(Map.Entry<String,String> entry:phoneSources.entrySet())try{
                rows.put(entry.getKey(),new JSONObject().put("error",error.getClass().getSimpleName())
                    .put("detail",error.getMessage()).put("source",entry.getValue()));
            }catch(JSONException ignored){}
        }
        sampleDeadline.set(System.nanoTime()+TimeUnit.MILLISECONDS.toNanos(400));
        WifiManager wifi=(WifiManager)c.getApplicationContext().getSystemService(Context.WIFI_SERVICE);
        put(rows,"wifi_mac","WifiInfo.getMacAddress",()->wifi.getConnectionInfo().getMacAddress());
        put(rows,"ssid","WifiInfo.getSSID",()->wifi.getConnectionInfo().getSSID());
        put(rows,"bssid","WifiInfo.getBSSID",()->wifi.getConnectionInfo().getBSSID());
        put(rows,"java_macs","NetworkInterface.getHardwareAddress",()->{
            JSONObject all=new JSONObject();Enumeration<NetworkInterface> interfaces=NetworkInterface.getNetworkInterfaces();
            while(interfaces!=null&&interfaces.hasMoreElements()){
                NetworkInterface item=interfaces.nextElement();all.put(item.getName(),bytes(item.getHardwareAddress(),":"));
            }return all;
        });
        put(rows,"bt_mac","BluetoothAdapter.getAddress",()->{
            BluetoothAdapter adapter=BluetoothAdapter.getDefaultAdapter();return adapter==null?null:adapter.getAddress();
        });
        LocationManager location=(LocationManager)c.getSystemService(Context.LOCATION_SERVICE);
        for(String id:new String[]{"latitude","longitude","accuracy"})put(rows,id,"LocationManager.getLastKnownLocation(gps)",()->{
            Location latest=location.getLastKnownLocation("gps");if(latest==null)return null;
            return id.equals("latitude")?latest.getLatitude():id.equals("longitude")?latest.getLongitude():latest.getAccuracy();
        });
        put(rows,"drm_id","MediaDrm Widevine deviceUniqueId",()->{
            MediaDrm drm=new MediaDrm(UUID.fromString("edef8ba9-79d6-4ace-a3c8-27dcd51d21ed"));
            try{return bytes(drm.getPropertyByteArray("deviceUniqueId"),"");}finally{drm.close();}
        });
        for(String id:new String[]{"width","height","density"})put(rows,id,"Display.getRealMetrics",()->{
            DisplayMetrics m=new DisplayMetrics();display.getRealMetrics(m);
            return id.equals("width")?m.widthPixels:id.equals("height")?m.heightPixels:m.densityDpi;
        });
        put(rows,"display_size","Display.getSize",()->{Point p=new Point();display.getSize(p);return p.x+" × "+p.y;});
        put(rows,"mode","Display.Mode physical dimensions",()->display.getMode().getPhysicalWidth()+" × "+display.getMode().getPhysicalHeight());
        put(rows,"resource_metrics","Resources.getDisplayMetrics",()->{
            DisplayMetrics m=c.getResources().getDisplayMetrics();return m.widthPixels+" × "+m.heightPixels+" / "+m.densityDpi;
        });
        put(rows,"total_ram","ActivityManager.MemoryInfo.totalMem bytes",()->{
            ActivityManager.MemoryInfo info=new ActivityManager.MemoryInfo();
            ((ActivityManager)c.getSystemService(Context.ACTIVITY_SERVICE)).getMemoryInfo(info);return info.totalMem;
        });
        put(rows,"storage","StatFs.getTotalBytes bytes",()->new StatFs(c.getFilesDir().getAbsolutePath()).getTotalBytes());
        put(rows,"memory_view","ActivityManager.MemoryInfo actual object",()->{
            ActivityManager.MemoryInfo info=new ActivityManager.MemoryInfo();
            ((ActivityManager)c.getSystemService(Context.ACTIVITY_SERVICE)).getMemoryInfo(info);
            return new JSONObject().put("total",info.totalMem).put("available",info.availMem)
                .put("threshold",info.threshold).put("lowMemory",info.lowMemory);
        });
        put(rows,"storage_view","StatFs blocks / bytes and File space actual APIs",()->{
            java.io.File path=c.getFilesDir();StatFs fs=new StatFs(path.getAbsolutePath());
            StatFs system=new StatFs("/system");
            return new JSONObject().put("blockSize",fs.getBlockSizeLong()).put("total",fs.getTotalBytes())
                .put("available",fs.getAvailableBytes()).put("free",fs.getFreeBytes())
                .put("blocks",fs.getBlockCountLong()).put("availableBlocks",fs.getAvailableBlocksLong())
                .put("freeBlocks",fs.getFreeBlocksLong()).put("blocks32",fs.getBlockCount())
                .put("availableBlocks32",fs.getAvailableBlocks()).put("freeBlocks32",fs.getFreeBlocks())
                .put("fileTotal",path.getTotalSpace()).put("fileFree",path.getFreeSpace())
                .put("fileUsable",path.getUsableSpace()).put("systemTotal",system.getTotalBytes());
        });
        put(rows,"typed_properties","SystemProperties.getInt / getLong / getBoolean",()->{
            Class<?> props=Class.forName("android.os.SystemProperties");
            return new JSONObject()
                .put("densityInt",props.getMethod("getInt",String.class,int.class).invoke(null,"ro.sf.lcd_density",-17))
                .put("densityLong",props.getMethod("getLong",String.class,long.class).invoke(null,"ro.sf.lcd_density",-17L))
                .put("missingInt",props.getMethod("getInt",String.class,int.class).invoke(null,"appstate.probe.absent",-17))
                .put("missingBool",props.getMethod("getBoolean",String.class,boolean.class).invoke(null,"appstate.probe.absent",true));
        });
        put(rows,"timezone","TimeZone.getDefault",()->TimeZone.getDefault().getID());
        put(rows,"language","Locale.getDefault",()->Locale.getDefault().toLanguageTag());
        put(rows,"hide_sensors","SensorManager.getSensorList count",()->((SensorManager)c.getSystemService(Context.SENSOR_SERVICE)).getSensorList(Sensor.TYPE_ALL).size());
        put(rows,"hide_module_apps","PackageManager module application count",()->ModuleListProbe.count(c));
        put(rows,"java_properties","SystemProperties.get",()->{
            JSONObject props=new JSONObject();
            for(String key:new String[]{"ro.product.model","ro.product.brand","ro.product.manufacturer","ro.build.fingerprint",
                "ro.product.device","ro.product.name","ro.product.board","ro.product.vendor.device","ro.product.odm.name",
                "ro.product.system_ext.manufacturer","ro.product.system_ext.device","ro.product.system_ext.name",
                "ro.system.build.fingerprint","ro.system_ext.build.fingerprint","ro.vendor.build.fingerprint",
                "ro.product.build.fingerprint","ro.odm.build.fingerprint","ro.vendor.build.version.release",
                "ro.serialno","ro.hardware","ro.boot.selinux","sys.usb.config"})
                props.put(key,property(key));return props;
        });
        put(rows,"metadata_properties","SystemProperties.get root / partition build metadata",()->{
            JSONObject properties=new JSONObject();
            for(String part:new String[]{"","system.","system_ext.","vendor.","product.","odm."})
                for(String field:new String[]{"id","type","tags"})
                    properties.put("ro."+part+"build."+field,property("ro."+part+"build."+field));
            return properties;
        });
        put(rows,"native","Bionic property get / read / callback and getifaddrs",()->{
            if(!nativeLoaded){System.loadLibrary("machineprobe");nativeLoaded=true;}return new JSONObject(nativeSnapshot());
        });
        if(BuildConfig.DEBUG)put(rows,"fixtures","Debug-only synthetic OEM / callback / Parcel controls",()->
            Class.forName("io.github.lwtdzh.screenshotdetector.MachineFixtures").getMethod("read",Context.class).invoke(null,c));
        put(rows,"ordinary","Unrelated settings, files, property defaults",()->{
            JSONObject control=new JSONObject();
            control.put("brightness",Settings.System.getInt(c.getContentResolver(),"screen_brightness",-1));
            control.put("propertyMissing",property("appstate.probe.absent"));
            control.put("localeExplicit",Locale.US.toLanguageTag());
            control.put("timezoneExplicit",TimeZone.getTimeZone("UTC").getID());
            StatFs fs=new StatFs(c.getFilesDir().getAbsolutePath());control.put("availableBytes",fs.getAvailableBytes());
            java.io.File file=new java.io.File(c.getCacheDir(),"ordinary-device-probe.txt");
            try {
                try(java.io.FileOutputStream out=new java.io.FileOutputStream(file)){out.write("ordinary-device-control".getBytes(java.nio.charset.StandardCharsets.UTF_8));}
                try(java.io.FileInputStream in=new java.io.FileInputStream(file)){
                    byte[] data=new byte[64];int count=in.read(data);control.put("file",new String(data,0,count,java.nio.charset.StandardCharsets.UTF_8));
                }
            }finally{file.delete();}return control;
        });
        try{result.put("reads",rows);}catch(JSONException ignored){}sampleDeadline.remove();return result;
    }
    private static String bytes(byte[] data,String delimiter) {
        if(data==null)return null;StringJoiner result=new StringJoiner(delimiter);
        for(byte value:data)result.add(String.format(Locale.ROOT,"%02x",value&255));return result.toString();
    }
}
