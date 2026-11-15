package io.github.lwtdzh.screenshotdetector;

import android.Manifest;
import android.app.Activity;
import android.content.*;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.os.*;
import android.text.*;
import android.view.*;
import android.widget.*;
import io.github.lwtdzh.deviceprofile.DeviceField;
import org.json.*;
import java.text.SimpleDateFormat;
import java.util.*;

/** Foreground two-second observations; direct values and read failures have equal visibility. */
public class DeviceActivity extends Activity {
    private DeviceSampler sampler;
    private final Map<String,TextView> rows=new LinkedHashMap<>();
    private final Map<String,View> fieldViews=new LinkedHashMap<>(),groupViews=new LinkedHashMap<>();
    private final Map<String,String> previous=new HashMap<>();
    private TextView summary,details;
    private boolean zh;
    private static final String[] GROUPS={"ids","network","model","location","environment"};
    private static final String[][] EXTRA={
        {"device_id","Telephony device ID"},{"serial_static","Build.SERIAL"},
        {"java_macs","Java · 网卡 MAC / Network MAC"},{"native_macs","Native · 网卡 MAC / Network MAC"},
        {"android_id_cursor","Android ID · ContentProvider"},{"xiaomi_oaid","OAID · Xiaomi SDK"},
        {"lte_ci","LTE · CI"},{"lte_mcc","LTE · MCC"},{"lte_mnc","LTE · MNC"},
        {"sim_state","SIM 状态 / SIM state"},{"sim_state_slot0","卡槽 1 状态 / Slot 1 state"},
        {"sim_state_slot1","卡槽 2 状态 / Slot 2 state"},{"sim_card_state","SIM 卡状态 / Card state"},
        {"sim_application_state","SIM 应用状态 / Application state"},{"has_sim","是否有 SIM / SIM present"},
        {"sim_operator","SIM 运营商代码 / SIM operator"},{"sim_operator_name","SIM 运营商 / SIM carrier"},
        {"sim_country","SIM 国家 / SIM country"},{"network_country","网络国家 / Network country"},
        {"network_type","数据网络类型 / Data network"},{"voice_network_type","语音网络类型 / Voice network"},
        {"data_state","数据连接状态 / Data connection"},{"roaming","漫游 / Roaming"},
        {"subscription_count","有效订阅数 / Active subscriptions"},{"default_subscription","默认数据订阅 / Default data subscription"},
        {"subscriptions","订阅详细信息 / Subscription details"},{"service_state","网络注册状态 / Service state"},
        {"cells","同步基站读取 / Synchronous cells"},{"async_cells","异步基站读取 / Asynchronous cells"},
        {"display_size","Display.getSize"},{"mode","Display.Mode"},{"resource_metrics","Resources metrics"},
        {"build_metadata","编译编号、类型与 API / Build metadata"},
        {"metadata_properties","各分区编译信息 / Partition build metadata"},
        {"typed_properties","类型化系统属性 / Typed properties"},
        {"memory_view","内存总量与可用量 / Memory capacity"},
        {"storage_view","数据分区块数与剩余量 / Data filesystem capacity"}};
    private String t(String cn,String en){return zh?cn:en;}
    private int dp(int n){return Math.round(n*getResources().getDisplayMetrics().density);}
    private LinearLayout column(){LinearLayout l=new LinearLayout(this);l.setOrientation(LinearLayout.VERTICAL);return l;}
    private TextView text(String s,int size,int color){
        TextView v=new TextView(this);v.setText(s);v.setTextSize(size);v.setTextColor(color);v.setPadding(0,dp(5),0,dp(5));return v;
    }
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);zh=getResources().getConfiguration().getLocales().get(0).getLanguage().equals("zh");
        LinearLayout root=column();root.setBackgroundColor(0xfff2f4f8);root.setPadding(dp(18),dp(28),dp(18),dp(12));
        root.setOnApplyWindowInsetsListener((v,i)->{
            if(Build.VERSION.SDK_INT>=30){
                android.graphics.Insets s=i.getInsets(WindowInsets.Type.systemBars()|WindowInsets.Type.displayCutout());
                v.setPadding(dp(18)+s.left,s.top,dp(18)+s.right,s.bottom);
            }return i;
        });
        Button back=new Button(this);back.setText(t("‹ 返回","‹ Back"));back.setOnClickListener(v->finish());root.addView(back);
        root.addView(text(t("设备信息 · 实际读取","Device information · actual reads"),23,0xff182331));
        summary=text(t("正在读取…","Reading…"),14,0xff175bc1);summary.setContentDescription("machine-summary");root.addView(summary);
        root.addView(text(t("每 2 秒刷新，离开页面暂停。值来自本应用系统接口；无法读取、缺少厂商服务与未注入都单独显示。",
            "Refreshes every 2 seconds while visible. Values come from this app's API reads. Errors, missing OEM services and injection state are shown."),13,0xff667085));
        Button grants=new Button(this);grants.setText(t("允许读取电话、位置与附近设备","Allow phone, location and nearby-device reads"));
        grants.setOnClickListener(v->{
            List<String> permissions=new ArrayList<>(Arrays.asList(Manifest.permission.READ_PHONE_STATE,
                Manifest.permission.ACCESS_FINE_LOCATION,Manifest.permission.ACCESS_COARSE_LOCATION));
            if(Build.VERSION.SDK_INT>=31)permissions.add(Manifest.permission.BLUETOOTH_CONNECT);
            requestPermissions(permissions.toArray(new String[0]),41);
        });root.addView(grants);
        EditText search=new EditText(this);search.setSingleLine(true);
        search.setHint(t("搜索全部 46 项，如 IMEI、OAID、MAC","Search all 46 fields, e.g. IMEI, OAID, MAC"));
        search.setContentDescription("machine-field-search");root.addView(search);
        ScrollView scroll=new ScrollView(this);LinearLayout body=column();scroll.addView(body);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        for(String group:GROUPS){
            LinearLayout card=column();card.setPadding(dp(16),dp(12),dp(16),dp(12));
            GradientDrawable bg=new GradientDrawable();bg.setColor(Color.WHITE);bg.setCornerRadius(dp(16));card.setBackground(bg);
            LinearLayout.LayoutParams layout=new LinearLayout.LayoutParams(-1,-2);layout.setMargins(0,dp(7),0,dp(7));body.addView(card,layout);
            groupViews.put(group,card);
            card.addView(text(DeviceField.groupName(group,zh),19,0xff182331));
            for(DeviceField field:DeviceField.ALL)if(field.group.equals(group)){
                LinearLayout fieldView=column();card.addView(fieldView);fieldViews.put(field.id,fieldView);
                fieldView.addView(text(t(field.zh,field.en),14,0xff182331));
                TextView row=text("—",13,0xff667085);row.setTextIsSelectable(true);row.setContentDescription("machine-read:"+field.id);
                rows.put(field.id,row);fieldView.addView(row);
            }
        }
        body.addView(text(t("更多读取入口与调试信息","Additional reads and debug details"),19,0xff182331));
        for(String[] extra:EXTRA){
            LinearLayout item=column();item.addView(text(extra[1],14,0xff182331));body.addView(item);
            TextView value=text("—",13,0xff667085);value.setTextIsSelectable(true);
            value.setContentDescription("machine-read:"+extra[0]);rows.put(extra[0],value);fieldViews.put(extra[0],item);item.addView(value);
        }
        Button debug=new Button(this);debug.setText(t("展开 / 收起原始调试信息","Show / hide raw debug details"));body.addView(debug);
        details=text("",12,0xff667085);details.setTextIsSelectable(true);details.setVisibility(View.GONE);body.addView(details);
        debug.setOnClickListener(v->details.setVisibility(details.getVisibility()==View.GONE?View.VISIBLE:View.GONE));
        search.addTextChangedListener(new TextWatcher(){
            public void beforeTextChanged(CharSequence s,int a,int c,int after){}
            public void afterTextChanged(Editable e){}
            public void onTextChanged(CharSequence s,int a,int before,int count){filter(s.toString());}
        });
        if(saved!=null)search.setText(saved.getString("machine-query",""));
        search.setTag("machine-search");
        sampler=new DeviceSampler(this,"machine-result.json",this::render);
        setContentView(root);
    }
    private void filter(String query){
        String q=query.trim().toLowerCase(Locale.ROOT);Map<String,Boolean> visible=new HashMap<>();
        for(DeviceField f:DeviceField.ALL){
            boolean show=(f.id+" "+f.zh+" "+f.en+" "+DeviceField.groupName(f.group,zh)).toLowerCase(Locale.ROOT).contains(q);
            fieldViews.get(f.id).setVisibility(show?View.VISIBLE:View.GONE);
            if(show)visible.put(f.group,true);
        }
        for(String group:GROUPS)groupViews.get(group).setVisibility(visible.containsKey(group)?View.VISIBLE:View.GONE);
        for(String[] extra:EXTRA)fieldViews.get(extra[0]).setVisibility(
            (extra[0]+" "+extra[1]).toLowerCase(Locale.ROOT).contains(q)?View.VISIBLE:View.GONE);
    }
    private void render(JSONObject result){
        JSONObject module=result.optJSONObject("module"),reads=result.optJSONObject("reads");
        if(reads==null)return;int changed=0;
        for(Map.Entry<String,TextView> entry:rows.entrySet()){
            JSONObject read=reads.optJSONObject(entry.getKey());
            if("native_macs".equals(entry.getKey())){
                JSONObject nativeRead=reads.optJSONObject("native");
                if(nativeRead!=null&&!nativeRead.has("error")){
                    JSONObject nativeValue=nativeRead.optJSONObject("value");
                    read=new JSONObject();
                    try{read.put("value",nativeValue==null?JSONObject.NULL:nativeValue.opt("interfaces"))
                        .put("source","getifaddrs / AF_PACKET");}catch(JSONException ignored){}
                }else read=nativeRead;
            }
            if(read==null)continue;
            String value=DevicePresentation.value(read,entry.getKey(),zh);
            String old=previous.put(entry.getKey(),value);boolean differs=old!=null&&!old.equals(value);if(differs)changed++;
            entry.getValue().setText((differs?t("已变化 · ","Changed · "):"")+value+"\n"+read.optString("source"));
            entry.getValue().setTextColor(differs?0xff175bc1:0xff667085);
        }
        String time=new SimpleDateFormat("HH:mm:ss",Locale.getDefault()).format(new Date(result.optLong("timestamp")));
        boolean injected=module!=null&&module.optBoolean("injected"),enabled=module!=null&&module.optBoolean("deviceEnabled");
        summary.setText(time+" · PID "+result.optInt("pid")+" · "+t("机器伪装 ","Device spoofing ")+
            (injected?(enabled?t("已开启","on"):t("已关闭","off")):t("未注入","not injected"))+
            " · "+t("位置 ","Location ")+(injected?(enabled&&module.optBoolean("locationEnabled")?t("已开启","on"):t("已关闭","off")):t("未注入","not injected"))+
            " · "+t("网络 ","Network ")+(injected&&enabled?("simulate".equals(module.optString("networkMode"))?t("有 SIM","SIM"):
                "no_sim".equals(module.optString("networkMode"))?t("无 SIM","no SIM"):t("真实读数","real")):t("真实读数","real"))+
            " · "+changed+t(" 项变化"," changed"));
        try{details.setText(result.toString(2));}catch(JSONException ignored){}
    }
    @Override protected void onResume(){super.onResume();sampler.start();}
    @Override protected void onPause(){sampler.stop();super.onPause();}
    @Override protected void onDestroy(){sampler.stop();super.onDestroy();}
    @Override protected void onSaveInstanceState(Bundle out){
        EditText search=getWindow().getDecorView().findViewWithTag("machine-search");
        if(search!=null)out.putString("machine-query",search.getText().toString());
        super.onSaveInstanceState(out);
    }
}
