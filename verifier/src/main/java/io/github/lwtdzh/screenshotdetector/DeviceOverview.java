package io.github.lwtdzh.screenshotdetector;

import android.app.Activity;
import android.content.Intent;
import android.graphics.drawable.GradientDrawable;
import android.widget.*;
import org.json.JSONObject;
import java.text.SimpleDateFormat;
import java.util.*;

/** Device identifiers visible directly on both the modern and legacy home pages. */
public final class DeviceOverview extends LinearLayout {
    private final boolean zh;
    private final TextView status;
    private final Map<String,TextView> rows=new LinkedHashMap<>();
    private final DeviceSampler sampler;
    public DeviceOverview(Activity activity){
        super(activity);zh=getResources().getConfiguration().getLocales().get(0).getLanguage().equals("zh");
        setOrientation(VERTICAL);setPadding(dp(14),dp(10),dp(14),dp(10));
        GradientDrawable bg=new GradientDrawable();bg.setColor(0xffedf3fc);bg.setCornerRadius(dp(14));setBackground(bg);
        addView(text(t("设备标识 · 实际读取","Device identifiers · actual reads"),18));
        String[] ids={"imei","imei2","android_id","oaid","serial","model"};
        String[] labels={t("IMEI · 卡槽 1","IMEI · slot 1"),t("IMEI · 卡槽 2","IMEI · slot 2"),
            "Android ID","OAID",t("设备序列号","Serial"),t("机型","Model")};
        for(int i=0;i<ids.length;i+=2){
            LinearLayout pair=new LinearLayout(activity);
            for(int j=i;j<i+2;j++){
                LinearLayout cell=new LinearLayout(activity);cell.setOrientation(VERTICAL);cell.setPadding(0,0,dp(8),0);
                cell.addView(text(labels[j],13));
                TextView value=text(t("正在读取…","Reading…"),13);value.setTextIsSelectable(true);
                value.setContentDescription("machine-overview:"+ids[j]);rows.put(ids[j],value);cell.addView(value);
                pair.addView(cell,new LinearLayout.LayoutParams(0,-2,1));
            }addView(pair);
        }
        status=text(t("每 2 秒更新，离开页面暂停","Updates every 2 seconds while visible"),12);
        status.setContentDescription("machine-home-summary");addView(status);
        Button full=new Button(activity);full.setText(t("查看全部 46 项 · MAC / SIM / 基站 / 屏幕",
            "All 46 fields · MAC / SIM / cell / display"));full.setTextSize(12);full.setContentDescription("machine-probe");
        full.setOnClickListener(v->activity.startActivity(new Intent(activity,DeviceActivity.class)));addView(full);
        sampler=new DeviceSampler(activity,"machine-home-result.json",this::render);
    }
    private String t(String cn,String en){return zh?cn:en;}
    private int dp(int n){return Math.round(n*getResources().getDisplayMetrics().density);}
    private TextView text(String s,int size){
        TextView v=new TextView(getContext());v.setText(s);v.setTextSize(size);v.setTextColor(0xff182331);
        v.setPadding(0,dp(3),0,dp(3));return v;
    }
    private void render(JSONObject result){
        JSONObject reads=result.optJSONObject("reads"),module=result.optJSONObject("module");if(reads==null)return;
        for(Map.Entry<String,TextView> row:rows.entrySet())
            row.getValue().setText(DevicePresentation.overview(reads.optJSONObject(row.getKey()),row.getKey(),zh));
        String time=new SimpleDateFormat("HH:mm:ss",Locale.getDefault()).format(new Date(result.optLong("timestamp")));
        status.setText(time+t(" · 每 2 秒 · 机器伪装："," · every 2 seconds · spoofing: ")+
            (module==null||!module.optBoolean("injected")?t("未注入","not injected"):
                module.optBoolean("deviceEnabled")?t("已开启","on"):t("已关闭","off")));
    }
    public void start(){sampler.start();}
    public void stop(){sampler.stop();}
}
