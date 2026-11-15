package io.github.lwtdzh.screenshotdetector;

import android.app.Service;
import android.content.*;
import android.os.*;
import android.telephony.*;
import android.telephony.gsm.GsmCellLocation;
import org.json.*;
import java.util.*;
import java.util.concurrent.*;

/**
 * Real phone APIs in a disposable, same-UID process. Interrupting a Future cannot
 * cancel a synchronous Binder transaction; ending this worker can.
 */
public final class PhoneReadService extends Service {
    private final Handler main=new Handler(Looper.getMainLooper());
    private boolean reading;
    private void exit() {
        // Never terminate an Activity process if the manifest is accidentally changed.
        if(android.app.Application.getProcessName().endsWith(":phone_reads"))
            android.os.Process.killProcess(android.os.Process.myPid());
    }
    private final Messenger endpoint=new Messenger(new Handler(Looper.getMainLooper(),message->{
        if(message.what==2){exit();return true;}
        if(message.what!=1 || message.replyTo==null)return true;
        if(reading)return true;
        reading=true;
        Messenger reply=message.replyTo;
        new Thread(()->{
            JSONObject sample=collect();
            Message response=Message.obtain(null,1);Bundle data=new Bundle();
            data.putString("sample",sample.toString());response.setData(data);
            try{reply.send(response);}catch(RemoteException ignored){}
            // Allow the reply to leave Binder before releasing outstanding calls.
            main.postDelayed(this::exit,100);
        },"PhoneSample").start();
        return true;
    }));
    @Override public IBinder onBind(Intent intent){return endpoint.getBinder();}

    @SuppressWarnings({"deprecation","MissingPermission"})
    private JSONObject collect() {
        TelephonyManager t=getSystemService(TelephonyManager.class);
        Map<String,Callable<Object>> reads=new LinkedHashMap<>();
        reads.put("imei",()->t.getImei(0));reads.put("imei2",()->t.getImei(1));
        reads.put("device_id",t::getDeviceId);reads.put("meid",t::getMeid);
        reads.put("imsi",t::getSubscriberId);reads.put("iccid",t::getSimSerialNumber);
        reads.put("phone",t::getLine1Number);reads.put("operator",t::getNetworkOperatorName);
        reads.put("mcc",()->operator(t,true));reads.put("mnc",()->operator(t,false));
        reads.put("sim_state",t::getSimState);reads.put("sim_state_slot0",()->t.getSimState(0));
        reads.put("sim_state_slot1",()->t.getSimState(1));
        reads.put("sim_card_state",()->TelephonyManager.class.getDeclaredMethod("getSimCardState").invoke(t));
        reads.put("sim_application_state",()->TelephonyManager.class.getDeclaredMethod("getSimApplicationState").invoke(t));
        reads.put("has_sim",t::hasIccCard);
        reads.put("sim_operator",t::getSimOperator);reads.put("sim_operator_name",t::getSimOperatorName);
        reads.put("sim_country",t::getSimCountryIso);reads.put("network_country",t::getNetworkCountryIso);
        reads.put("network_type",t::getDataNetworkType);reads.put("voice_network_type",t::getVoiceNetworkType);
        reads.put("data_state",t::getDataState);reads.put("roaming",t::isNetworkRoaming);
        SubscriptionManager subscriptions=getSystemService(SubscriptionManager.class);
        reads.put("subscription_count",subscriptions::getActiveSubscriptionInfoCount);
        reads.put("default_subscription",SubscriptionManager::getDefaultDataSubscriptionId);
        reads.put("subscriptions",()->{
            JSONArray list=new JSONArray();List<SubscriptionInfo> active=subscriptions.getActiveSubscriptionInfoList();
            if(active!=null)for(SubscriptionInfo item:active){
                Parcel parcel=Parcel.obtain();
                try{
                    item.writeToParcel(parcel,0);parcel.setDataPosition(0);
                    SubscriptionInfo copy=SubscriptionInfo.CREATOR.createFromParcel(parcel);
                    list.put(new JSONObject().put("id",item.getSubscriptionId()).put("slot",item.getSimSlotIndex())
                        .put("iccid",item.getIccId()).put("mcc",Build.VERSION.SDK_INT>=29?item.getMccString():String.valueOf(item.getMcc()))
                        .put("mnc",Build.VERSION.SDK_INT>=29?item.getMncString():String.valueOf(item.getMnc()))
                        .put("carrier",item.getCarrierName()).put("phone",item.getNumber()).put("country",item.getCountryIso())
                        .put("parcelIccid",copy.getIccId())
                        .put("parcelMcc",Build.VERSION.SDK_INT>=29?copy.getMccString():String.valueOf(copy.getMcc()))
                        .put("parcelMnc",Build.VERSION.SDK_INT>=29?copy.getMncString():String.valueOf(copy.getMnc())));
                }finally{parcel.recycle();}
            }return list;
        });
        reads.put("service_state",()->{
            ServiceState service=t.getServiceState();if(service==null)return null;
            JSONArray registrations=new JSONArray();
            if(Build.VERSION.SDK_INT>=30)for(NetworkRegistrationInfo entry:service.getNetworkRegistrationInfoList())
                registrations.put(new JSONObject().put("domain",entry.getDomain()).put("registered",entry.isRegistered())
                    .put("technology",entry.getAccessNetworkTechnology()));
            return new JSONObject().put("state",service.getState()).put("operator",service.getOperatorAlphaLong())
                .put("numeric",service.getOperatorNumeric()).put("roaming",service.getRoaming()).put("registrations",registrations);
        });
        reads.put("cells",()->cellList(t.getAllCellInfo()));
        reads.put("async_cells",()->{
            if(Build.VERSION.SDK_INT<29)throw new UnsupportedOperationException("CellInfoCallback requires Android 10+");
            CompletableFuture<List<CellInfo>> reply=new CompletableFuture<>();
            t.requestCellInfoUpdate(Runnable::run,new TelephonyManager.CellInfoCallback(){
                @Override public void onCellInfo(List<CellInfo> cells){reply.complete(cells);}
                @Override public void onError(int code,Throwable detail){
                    reply.completeExceptionally(detail==null?new IllegalStateException("Cell callback error "+code):detail);
                }
            });
            return cellList(reply.get(650,TimeUnit.MILLISECONDS));
        });
        reads.put("lac",()->{CellLocation c=t.getCellLocation();return c instanceof GsmCellLocation?((GsmCellLocation)c).getLac():null;});
        reads.put("cid",()->{CellLocation c=t.getCellLocation();return c instanceof GsmCellLocation?((GsmCellLocation)c).getCid():null;});
        for(String id:new String[]{"tac","pci","lte_ci","lte_mcc","lte_mnc","signal"})reads.put(id,()->{
            List<CellInfo> cells=t.getAllCellInfo();
            if(cells!=null)for(CellInfo cell:cells)if(cell instanceof CellInfoLte){
                CellInfoLte lte=(CellInfoLte)cell;CellIdentityLte identity=lte.getCellIdentity();
                switch(id){
                    case "tac":return identity.getTac();case "pci":return identity.getPci();case "lte_ci":return identity.getCi();
                    case "lte_mcc":return identity.getMccString();case "lte_mnc":return identity.getMncString();
                    default:return lte.getCellSignalStrength().getDbm();
                }
            }return null;
        });
        ExecutorService pool=Executors.newFixedThreadPool(reads.size());
        Map<String,Future<Object>> pending=new LinkedHashMap<>();
        reads.forEach((id,read)->pending.put(id,pool.submit(read)));
        long deadline=SystemClock.elapsedRealtime()+800;
        JSONObject result=new JSONObject(),rows=new JSONObject();
        try {
            for(Map.Entry<String,Future<Object>> entry:pending.entrySet()){
                JSONObject row=new JSONObject();
                try {
                    Object value=entry.getValue().get(Math.max(0,deadline-SystemClock.elapsedRealtime()),TimeUnit.MILLISECONDS);
                    row.put("value",value==null?JSONObject.NULL:value);
                }catch(Exception error){
                    Throwable cause=error instanceof ExecutionException?error.getCause():error;
                    row.put("error",cause.getClass().getSimpleName()).put("detail",cause.getMessage());
                }
                rows.put(entry.getKey(),row);
            }
            result.put("pid",android.os.Process.myPid())
                .put("revision",ModuleStatus.snapshot().getLong("deviceRevision")).put("reads",rows);
        }catch(JSONException ignored){}
        pool.shutdownNow();
        return result;
    }
    private static JSONArray cellList(List<CellInfo> cells)throws JSONException{
        JSONArray rows=new JSONArray();if(cells==null)return rows;
        for(CellInfo cell:cells)if(cell instanceof CellInfoLte){
            CellInfoLte lte=(CellInfoLte)cell;CellIdentityLte identity=lte.getCellIdentity();
            Parcel parcel=Parcel.obtain();
            try{
                cell.writeToParcel(parcel,0);parcel.setDataPosition(0);
                CellInfoLte copy=(CellInfoLte)CellInfo.CREATOR.createFromParcel(parcel);
                rows.put(new JSONObject().put("registered",cell.isRegistered()).put("mcc",identity.getMccString())
                    .put("mnc",identity.getMncString()).put("cid",identity.getCi()).put("tac",identity.getTac())
                    .put("pci",identity.getPci()).put("signal",lte.getCellSignalStrength().getDbm())
                    .put("parcelCid",copy.getCellIdentity().getCi()).put("parcelSignal",copy.getCellSignalStrength().getDbm()));
            }finally{parcel.recycle();}
        }else rows.put(new JSONObject().put("type",cell.getClass().getSimpleName()).put("registered",cell.isRegistered()));
        return rows;
    }
    private static String operator(TelephonyManager t,boolean mcc){
        String value=t.getNetworkOperator();
        return value!=null&&value.matches("\\d{5,6}")?(mcc?value.substring(0,3):value.substring(3)):null;
    }

    /** Called only on the shared sampling thread, never the UI thread. */
    static JSONObject read(Context context) throws Exception {
        CompletableFuture<JSONObject> result=new CompletableFuture<>();
        Messenger[] remote=new Messenger[1];
        Handler main=new Handler(Looper.getMainLooper());
        Messenger reply=new Messenger(new Handler(Looper.getMainLooper(),message->{
            try{result.complete(new JSONObject(message.getData().getString("sample")));}
            catch(Exception error){result.completeExceptionally(error);}
            return true;
        }));
        ServiceConnection connection=new ServiceConnection(){
            @Override public void onServiceConnected(ComponentName name,IBinder binder){
                remote[0]=new Messenger(binder);Message request=Message.obtain(null,1);request.replyTo=reply;
                try{remote[0].send(request);}catch(RemoteException error){result.completeExceptionally(error);}
            }
            @Override public void onServiceDisconnected(ComponentName name){
                result.completeExceptionally(new IllegalStateException("Phone worker disconnected"));
            }
        };
        boolean bound=context.bindService(new Intent(context,PhoneReadService.class),connection,Context.BIND_AUTO_CREATE);
        if(!bound)throw new IllegalStateException("Phone worker unavailable");
        try{return result.get(1700,TimeUnit.MILLISECONDS);}
        finally {
            CompletableFuture<Void> released=new CompletableFuture<>();
            main.post(()->{
                try{
                    if(remote[0]!=null)try{remote[0].send(Message.obtain(null,2));}catch(RemoteException ignored){}
                    context.unbindService(connection);
                }finally{released.complete(null);}
            });
            // The next foreground page must not bind while teardown is queued.
            released.get(1000,TimeUnit.MILLISECONDS);
        }
    }
}
