package io.github.lwtdzh.appstateshield;

import android.app.*;
import android.content.*;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.os.*;
import android.text.*;
import android.view.*;
import android.widget.*;
import io.github.lwtdzh.deviceprofile.*;
import java.util.*;

/** App-specific draft editor. It never adds a package to Vector scope. */
public final class DeviceSettingsActivity extends Activity {
    private DeviceStore store;
    private DeviceProfile original;
    private boolean enabled, modelEnabled, locationEnabled, zh;
    private String pkg, preset, query="";
    private String regionId="",regionName="";
    private String networkMode=DeviceProfile.NETWORK_NO_SIM;
    private final Set<String> regionOverrides=new LinkedHashSet<>();
    private ChinaRegions regions;
    private final Map<String,String> values=new LinkedHashMap<>();
    private final Set<String> selected=new LinkedHashSet<>(), expanded=new LinkedHashSet<>();
    private LinearLayout root,body,fields;
    private TextView status,saveHint,consistencyHint;
    private Switch master;
    private String t(String a,String b) { return zh?a:b; }
    private int dp(int n) { return Math.round(n*getResources().getDisplayMetrics().density); }
    private DeviceProfile draft() {
        return new DeviceProfile(enabled,original.revision,preset,values,selected,locationEnabled,regionId,regionName,regionOverrides,networkMode,modelEnabled);
    }
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        zh=getResources().getConfiguration().getLocales().get(0).getLanguage().equals("zh");
        pkg=getIntent().getStringExtra("package");
        if(pkg==null || pkg.equals(getPackageName())) { finish();return; }
        store=new DeviceStore(this);original=store.read(pkg);load(state==null?original:DeviceProfile.parse(state.getString("draft")));
        if(state!=null) {
            original=DeviceProfile.parse(state.getString("original"));query=state.getString("query","");
            ArrayList<String> groups=state.getStringArrayList("expanded");
            if(groups!=null){expanded.clear();expanded.addAll(groups);}
        }
        if(Build.VERSION.SDK_INT>=33) getOnBackInvokedDispatcher().registerOnBackInvokedCallback(0,this::back);
        render();
    }
    private void load(DeviceProfile p) {
        enabled=p.enabled;modelEnabled=p.modelEnabled;locationEnabled=p.locationEnabled;preset=p.preset;networkMode=p.networkMode;
        regionId=p.regionId;regionName=p.regionName;regionOverrides.clear();regionOverrides.addAll(p.regionOverrides);
        values.clear();values.putAll(p.values);selected.clear();selected.addAll(p.selected);
    }
    private LinearLayout column() { LinearLayout l=new LinearLayout(this);l.setOrientation(LinearLayout.VERTICAL);return l; }
    private TextView text(String s,int size,int color) {
        TextView v=new TextView(this);v.setText(s);v.setTextSize(size);v.setTextColor(color);v.setPadding(0,dp(4),0,dp(4));return v;
    }
    private void explanation(LinearLayout parent,String title,String body) {
        TextView heading=text(title,14,0xff182331);
        heading.setTypeface(null,android.graphics.Typeface.BOLD);
        LinearLayout.LayoutParams layout=new LinearLayout.LayoutParams(-1,-2);
        layout.topMargin=dp(10);parent.addView(heading,layout);
        TextView description=text(body,13,0xff667085);description.setLineSpacing(dp(3),1);
        parent.addView(description);
    }
    private void moreExplanation(LinearLayout parent,String id,String title,String body) {
        LinearLayout content=column();content.setVisibility(View.GONE);
        TextView description=text(body,13,0xff667085);description.setLineSpacing(dp(4),1);content.addView(description);
        Button toggle=button(title+"  ⌄",id,()->{});toggle.setGravity(Gravity.START|Gravity.CENTER_VERTICAL);
        toggle.setBackground(background(Color.WHITE,8));toggle.setTextSize(13);
        toggle.setOnClickListener(v->{
            boolean open=content.getVisibility()!=View.VISIBLE;
            content.setVisibility(open?View.VISIBLE:View.GONE);toggle.setText(title+(open?"  ⌃":"  ⌄"));
        });
        parent.addView(toggle);parent.addView(content);
    }
    private Button button(String label,String id,Runnable action) {
        Button b=new Button(this);b.setText(label);b.setAllCaps(false);b.setContentDescription(id);
        b.setTextSize(14);b.setTextColor(0xff175bc1);b.setBackground(background(0xffedf3ff,10));
        b.setElevation(0);b.setStateListAnimator(null);b.setMinHeight(dp(44));b.setMinimumHeight(dp(44));
        b.setPadding(dp(12),dp(8),dp(12),dp(8));b.setOnClickListener(v->action.run());return b;
    }
    private GradientDrawable background(int color,int radius) {
        GradientDrawable b=new GradientDrawable();b.setColor(color);b.setCornerRadius(dp(radius));return b;
    }
    private LinearLayout card(LinearLayout parent) {
        LinearLayout l=column();l.setPadding(dp(16),dp(12),dp(16),dp(12));l.setBackground(background(Color.WHITE,16));
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.setMargins(0,dp(6),0,dp(6));parent.addView(l,p);return l;
    }
    private void render() {
        root=column();root.setBackgroundColor(0xfff2f4f8);root.setPadding(dp(18),0,dp(18),0);
        root.setOnApplyWindowInsetsListener((v,i)->{
            if(Build.VERSION.SDK_INT>=30) {
                android.graphics.Insets s=i.getInsets(WindowInsets.Type.systemBars()|WindowInsets.Type.displayCutout());
                v.setPadding(dp(18)+s.left,s.top,dp(18)+s.right,s.bottom);
                if(v.getWindowInsetsController()!=null) v.getWindowInsetsController().setSystemBarsAppearance(
                    WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS|WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS,
                    WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS|WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS);
            }
            return i;
        });
        LinearLayout bar=new LinearLayout(this);bar.setGravity(Gravity.CENTER_VERTICAL);
        bar.addView(button("‹","device-back",this::back),new LinearLayout.LayoutParams(dp(52),-2));
        bar.addView(text(t("机器伪装","Device spoofing"),23,0xff182331));root.addView(bar);
        body=column();ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);scroll.addView(body);
        root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        LinearLayout app=card(body);LinearLayout identity=new LinearLayout(this);identity.setGravity(Gravity.CENTER_VERTICAL);
        try {
            ImageView icon=new ImageView(this);icon.setImageDrawable(getPackageManager().getApplicationIcon(pkg));
            identity.addView(icon,new LinearLayout.LayoutParams(dp(42),dp(42)));
            TextView name=text(getPackageManager().getApplicationLabel(getPackageManager().getApplicationInfo(pkg,0)).toString(),19,0xff182331);
            name.setPadding(dp(12),0,0,0);identity.addView(name);
        } catch(Exception e) { identity.addView(text(pkg,18,0xff182331)); }
        app.addView(identity);app.addView(text(pkg,12,0xff667085));
        master=new Switch(this);master.setText(t("为此应用开启机器伪装","Enable for this app"));master.setTextSize(17);
        master.setContentDescription("device-enabled");master.setChecked(enabled);app.addView(master);
        app.addView(text(t("默认关闭。仅影响此应用；仍需在 Vector 中选中它。",
            "Off by default. Only this app is affected; also select it in Vector."),13,0xff667085));
        master.setOnCheckedChangeListener((b,on)->{
            enabled=on;
            if(on && values.isEmpty()) load(DeviceProfile.preset("xiaomi-14"));
            renderContent();dirty();
        });
        fields=column();body.addView(fields);renderContent();
        LinearLayout footer=column();footer.setPadding(0,dp(8),0,dp(8));
        saveHint=text("",12,0xff667085);saveHint.setContentDescription("device-save-hint");footer.addView(saveHint);
        Button save=button(t("保存机器伪装","Save device profile"),"device-save",this::save);
        save.setBackgroundTintList(android.content.res.ColorStateList.valueOf(0xff175bc1));save.setTextColor(Color.WHITE);
        footer.addView(save);root.addView(footer);setContentView(root);dirty();
    }
    private void renderContent() {
        fields.removeAllViews();
        if(!enabled) {
            LinearLayout empty=card(fields);empty.addView(text(t("机器伪装已关闭","Device spoofing is off"),20,0xff182331));
            empty.addView(text(t(values.isEmpty()?"开启后默认伪装设备标识、模拟无 SIM 卡。机型与屏幕保持本机读数。":"原档案已保留，再次开启可继续使用。",
                values.isEmpty()?"Defaults to device identifiers and no SIM. Model and display keep their original readings.":"Your saved profile is retained for next time."),15,0xff667085));
            return;
        }
        LinearLayout p=card(fields);p.setBackground(background(0xffe8f0ff,16));
        status=text("",13,0xff475569);p.addView(status);
        consistencyHint=text("",13,0xff805600);
        consistencyHint.setContentDescription("device-consistency-hint");
        consistencyHint.setLineSpacing(dp(3),1);p.addView(consistencyHint);
        p.addView(text(t("默认只伪装设备标识、模拟无 SIM 卡。需要改机型与屏幕时，再开启这一节。",
            "Defaults to device identifiers and no SIM. Enable Model & system to change model and display readings."),13,0xff667085));
        EditText search=new EditText(this);search.setSingleLine(true);search.setHint(t("搜索字段，如 IMEI、位置","Search fields, e.g. IMEI, location"));
        search.setText(query);search.setContentDescription("device-field-search");fields.addView(search);
        LinearLayout groups=column();fields.addView(groups);renderGroups(groups);
        search.addTextChangedListener(new TextWatcher() {
            public void beforeTextChanged(CharSequence s,int a,int c,int after){}
            public void afterTextChanged(Editable e){}
            public void onTextChanged(CharSequence s,int a,int before,int count){query=s.toString();renderGroups(groups);}
        });
        LinearLayout note=card(fields);
        explanation(note,t("改完记得保存","Save your changes"),
            t("点击底部“保存机器伪装”，再到检测器查看结果。\n如果目标应用还显示旧信息，请彻底关闭后重新打开。",
              "Tap Save device profile, then check the verifier.\nIf an app still shows old values, close it completely and reopen it."));
        moreExplanation(note,"device-help:limits",t("了解伪装的作用范围","What spoofing changes"),
            t("• 只修改目标应用读取到的信息，不会更换手机硬件或实际连接。\n• 公网 IP 和硬件认证结果不会跟着变。\n• 屏幕参数会影响应用布局，修改后请检查显示是否正常。\n• 机型和系统参数使用已核实的数据；尚未取得真实数据的项目需手工填写。\n• Wi-Fi 名称取决于所连路由器，和手机型号无关。",
              "• Changes what the target app reads, without changing hardware or connections.\n• Public IP and hardware attestation remain unchanged.\n• Display values can affect layouts; check the app after editing.\n• Model and system values use verified data. Missing values require manual entry.\n• Wi-Fi names belong to routers, not phone models."));
        updateStatus();
    }
    private void renderGroups(LinearLayout groups) {
        groups.removeAllViews();String q=query.trim().toLowerCase(Locale.ROOT);int found=0;
        for(String group:Arrays.asList("ids","network","model","location","environment")) {
            List<DeviceField> list=new ArrayList<>();
            for(DeviceField f:DeviceField.ALL) if(f.group.equals(group)&&(q.isEmpty()||
                (f.id+" "+f.zh+" "+f.en+" "+DeviceField.groupName(group,zh)).toLowerCase(Locale.ROOT).contains(q))) list.add(f);
            if(list.isEmpty())continue;found+=list.size();
            LinearLayout card=card(groups);boolean open=!q.isEmpty()||expanded.contains(group);
            long count=list.stream().filter(f->selected.contains(f.id)).count();
            String gateState=group.equals("model")?t(modelEnabled?" · 已开启":" · 已关闭",modelEnabled?" · on":" · off"):"";
            Button title=button(DeviceField.groupName(group,zh)+gateState+"  "+count+"/"+list.size()+"  "+(open?"⌃":"⌄"),"device-group:"+group,()->{
                if(!expanded.remove(group))expanded.add(group);renderGroups(groups);
            });title.setGravity(Gravity.START|Gravity.CENTER_VERTICAL);title.setTextColor(0xff182331);
            title.setBackground(background(Color.WHITE,8));title.setTextSize(17);card.addView(title);
            if(!open)continue;
            if(group.equals("location"))renderLocation(card,groups);
            if(group.equals("network"))renderNetwork(card,groups);
            if(group.equals("model")){
                renderModelGate(card,groups);
                card.addView(button(t("按预设机型填写参数\n当前：","Fill values from a model preset\nCurrent: ")+presetTitle(),
                    "device-preset",this::choosePreset));
                renderModelSource(card);
            }
            if(group.equals("network")||group.equals("ids"))
                card.addView(button(t(group.equals("network")?"统一刷新网络参数":"统一刷新设备标识",
                    group.equals("network")?"Refresh network values":"Refresh device IDs"),
                    "device-group-refresh:"+group,()->refreshGroup(group)));
            for(DeviceField f:list) {
                if(f.id.equals("width"))card.addView(text(t("屏幕参数","Display values"),16,0xff175bc1));
                LinearLayout row=new LinearLayout(this);row.setGravity(Gravity.CENTER_VERTICAL);row.setPadding(0,dp(6),0,dp(6));
                LinearLayout label=column();label.setContentDescription("device-field:"+f.id);
                boolean gated=f.group.equals("model")&&!modelEnabled || f.group.equals("location")&&!locationEnabled ||
                    f.group.equals("network")&&(DeviceProfile.NETWORK_OFF.equals(networkMode)||
                        DeviceProfile.NETWORK_NO_SIM.equals(networkMode)&&DevicePackets.CELLULAR.contains(f.id));
                String state=!selected.contains(f.id)?t(" · 原始值"," · original"):
                    gated?(f.group.equals("model")?t(" · 待开启机型与系统"," · model off"):
                        f.group.equals("location")?t(" · 待开启位置"," · location off"):
                        DeviceProfile.NETWORK_NO_SIM.equals(networkMode)?t(" · 无 SIM 卡"," · no SIM"):t(" · 不模拟"," · off")):
                    t(" · 已选"," · selected");
                label.addView(text(t(f.zh,f.en)+state,15,
                    selected.contains(f.id)?0xff182331:0xff667085));
                String value=values.get(f.id);
                boolean unverified=value==null&&!ModelPresets.values(preset).containsKey(f.id)&&
                    (f.group.equals("model")||f.id.equals("density"));
                TextView shown=text(value==null?(unverified?t("尚未核实，请手工填写","Not verified; enter manually"):t("未填写","Not set")):value,13,0xff667085);
                shown.setMaxLines(2);shown.setEllipsize(TextUtils.TruncateAt.END);shown.setContentDescription("device-value:"+f.id);label.addView(shown);
                label.setOnClickListener(v->edit(f));row.addView(label,new LinearLayout.LayoutParams(0,-2,1));
                if(f.group.equals("location")||f.group.equals("network")){
                    Switch use=new Switch(this);use.setChecked(selected.contains(f.id));
                    use.setContentDescription("device-field-enabled:"+f.id);use.setEnabled(!gated);
                    boolean cellular=f.group.equals("network")&&DevicePackets.CELLULAR.contains(f.id);
                    if(cellular&&DeviceProfile.NETWORK_SIMULATE.equals(networkMode)){use.setChecked(true);use.setEnabled(false);}
                    use.setOnCheckedChangeListener((b,on)->{
                        if(on&&f.validate(values.get(f.id))!=null){use.setChecked(false);edit(f);return;}
                        if(on)selected.add(f.id);else selected.remove(f.id);
                        renderGroups(groups);dirty();
                    });
                    row.addView(use);
                }
                if(f.random) {
                    Button refresh=button("↻","device-random:"+f.id,()->{
                        values.put(f.id,f.generate());selected.add(f.id);markOverride(f);renderGroups(groups);dirty();
                    });refresh.setMinWidth(dp(48));refresh.setMinimumWidth(dp(48));
                    refresh.setEnabled(!gated);
                    LinearLayout.LayoutParams rp=new LinearLayout.LayoutParams(dp(44),dp(44));rp.setMargins(0,0,dp(6),0);
                    row.addView(refresh,rp);
                }
                Button edit=button(t("编辑","Edit"),"device-edit:"+f.id,()->edit(f));
                edit.setEnabled(!gated);label.setEnabled(!gated);
                edit.setTextSize(12);edit.setMinWidth(dp(52));edit.setMinimumWidth(dp(52));row.addView(edit);
                card.addView(row);
            }
        }
        if(found==0)groups.addView(text(t("没有匹配字段","No matching fields"),15,0xff667085));
        updateStatus();
    }
    private String presetTitle() {
        return "xiaomi-14".equals(preset)?t("小米 14 · 国际版","Xiaomi 14 · global"):
            "vivo-x200-pro-mini".equals(preset)?"vivo X200 Pro mini":t("自定义档案","Custom profile");
    }
    private void renderModelSource(LinearLayout card){
        if(ModelPresets.values(preset).isEmpty()){
            card.addView(text(t("自定义参数。需要预设数据时，请先选择机型。","Custom values. Choose a model to use preset data."),13,0xff667085));return;
        }
        card.addView(text(ModelPresets.version(preset),13,0xff175bc1));
        List<String> missing=ModelPresets.missing(preset,"model");
        if(!missing.isEmpty()){
            StringJoiner names=new StringJoiner("、");
            for(String id:missing){DeviceField f=DeviceField.find(id);names.add(t(f.zh,f.en));}
            explanation(card,t("这份预设还有未核实的项目","Some preset values are not verified"),
                t(names+"尚未取得真实数据，需手工填写。未填写的项目会读取本机原值。",
                  "Enter these values manually: "+names+". Unset values return this phone's original data."));
        }else card.addView(text(t("按这份预设填写下方机型、系统和屏幕参数。",
            "Use this preset to fill the model, system and display values below."),13,0xff667085));
    }
    private void choosePreset() {
        String[] names={t("小米 14 · 国际版","Xiaomi 14 · global"),"vivo X200 Pro mini"};
        new AlertDialog.Builder(this).setTitle(t("选择用于填写的机型","Choose a model to fill values")).setItems(names,(d,w)->
            new AlertDialog.Builder(this).setTitle(names[w]).setMessage(t("用这份预设填写下方机型、系统和屏幕参数，保存后生效。",
                "Fill the model, system and display values below from this preset. Save to apply."))
                .setNegativeButton(t("取消","Cancel"),null).setPositiveButton(t("填写参数","Fill values"),(a,b)->{
                    preset=w==0?"xiaomi-14":"vivo-x200-pro-mini";
                    Map<String,String> packet=DevicePackets.group("model",preset);
                    for(DeviceField f:DeviceField.ALL)if(f.group.equals("model")){
                        values.remove(f.id);selected.remove(f.id);
                    }
                    values.putAll(packet);selected.addAll(packet.keySet());renderContent();dirty();
                }).show()).show();
    }
    private void markOverride(DeviceField f){
        if(f.group.equals("location")&&!regionId.isEmpty())regionOverrides.add(f.id);
    }
    private void renderModelGate(LinearLayout card,LinearLayout groups) {
        Switch gate=new Switch(this);gate.setText(t("开启机型与系统伪装","Enable model & system spoofing"));
        gate.setContentDescription("device-model-enabled");gate.setChecked(modelEnabled);card.addView(gate);
        gate.setOnCheckedChangeListener((b,on)->{modelEnabled=on;renderGroups(groups);dirty();});
        card.addView(text(t("默认关闭。机型、系统与屏幕参数一起生效；关闭时保留参数，恢复本机读数。",
            "Off by default. Model, system and display values apply together. Turning it off retains values and restores original readings."),13,0xff667085));
    }
    private ChinaRegions regions()throws java.io.IOException {
        if(regions==null)regions=new ChinaRegions(getAssets().open("china-regions.tsv"));
        return regions;
    }
    private void renderLocation(LinearLayout card,LinearLayout groups){
        Switch gate=new Switch(this);gate.setText(t("开启位置伪装","Enable location spoofing"));
        gate.setContentDescription("device-location-enabled");gate.setChecked(locationEnabled);card.addView(gate);
        gate.setOnCheckedChangeListener((b,on)->{locationEnabled=on;renderGroups(groups);dirty();});
        card.addView(text(t("默认关闭。开启后，再选择需要伪装的位置项目。",
            "Off by default. Enable it, then choose which location values to spoof."),13,0xff667085));
        Button region=button(t("选择省 / 市 / 区","Choose province / city / district"),"device-region-picker",this::chooseRegion);
        region.setGravity(Gravity.START|Gravity.CENTER_VERTICAL);card.addView(region);
        TextView regionStatus=text(regionName.isEmpty()?t("尚未选择地区","No region selected"):
            regionName+(regionOverrides.isEmpty()?t(" · 按地区统一填写"," · region values"):
                t(" · "+regionOverrides.size()+" 项已单独修改"," · "+regionOverrides.size()+" manual overrides")),14,0xff175bc1);
        regionStatus.setContentDescription("device-region-status");card.addView(regionStatus);
        explanation(card,t("先选地区，再微调","Choose a region, then fine-tune"),
            t("选择省、市、区，会一起填写经度、纬度和精度。\n需要更具体的位置，可以编辑下面的数值。",
              "Selecting a province, city and district fills longitude, latitude and accuracy.\nEdit the values below for a more specific location."));
        moreExplanation(card,"device-help:location",t("位置数据说明","About location data"),
            t("• 使用地区内的一个代表点，不是街道或门牌地址。\n• 只更新经纬度和精度，基站参数在“网络与基站”中设置。\n• 地区数据更新于 2026 年 4 月，部分地区缺少坐标。\n• 关闭位置伪装会保留已填写的参数。",
              "• Uses a representative point, not a street address.\n• Only coordinates and accuracy change. Configure cells under Network & cell.\n• The April 2026 dataset has missing coordinates for some districts.\n• Turning location spoofing off preserves saved values."));
    }
    private void renderNetwork(LinearLayout card,LinearLayout groups){
        RadioGroup modes=new RadioGroup(this);modes.setOrientation(RadioGroup.VERTICAL);
        explanation(card,t("选择模拟方式","Choose a mode"),
            t("保存后，只影响当前应用看到的网络信息。",
              "After saving, this changes the network information seen by this app."));
        String[] ids={DeviceProfile.NETWORK_OFF,DeviceProfile.NETWORK_SIMULATE,DeviceProfile.NETWORK_NO_SIM};
        String[] labels={t("不模拟","Off"),t("打开模拟","Simulate network & cell"),t("模拟无 SIM 卡（默认）","Simulate no SIM (default)")};
        String[] descriptions={
            t("让应用读取真实的网络和 SIM 卡信息。","Let the app read real network and SIM information."),
            t("让应用看到一张已插入的 SIM 卡，以及匹配的运营商和基站信息。","Show one inserted SIM with matching carrier and cell information."),
            t("让应用认为没有插入 SIM 卡，也没有运营商和基站信息。","Show no inserted SIM, carrier or cell information.")};
        for(int i=0;i<ids.length;i++){
            RadioButton option=new RadioButton(this);option.setId(View.generateViewId());option.setText(labels[i]);
            option.setTextSize(15);
            option.setTag(ids[i]);option.setContentDescription("device-network-mode:"+ids[i]);modes.addView(option);
            TextView description=text(descriptions[i],13,0xff667085);
            description.setPadding(dp(32),0,dp(8),dp(10));description.setLineSpacing(dp(2),1);
            description.setContentDescription("device-network-description:"+ids[i]);
            final int optionId=option.getId();description.setOnClickListener(v->modes.check(optionId));
            modes.addView(description);
            if(ids[i].equals(networkMode))modes.check(option.getId());
        }
        card.addView(modes);
        modes.setOnCheckedChangeListener((g,id)->{
            networkMode=(String)g.findViewById(id).getTag();renderGroups(groups);dirty();
        });
        explanation(card,t("参数怎么改","Edit the values"),
            t("一起换：点“统一刷新网络参数”，生成相互匹配的一组信息。\n单独改：点下面的“编辑”或 ↻，只修改这一项。",
              "Change the set: tap Refresh network values to generate matching information.\nChange one value: use Edit or ↻ beside it."));
        moreExplanation(card,"device-help:network",t("使用须知","Things to know"),
            t("• 单独修改可能让运营商和基站对不上，统一刷新可重新匹配。\n• “打开模拟”时，SIM 卡、运营商和基站信息一起生效。\n• Wi-Fi 和蓝牙可以分别设置；“不模拟”时也会恢复真实信息。\n• 切换模式会保留已填写的参数，改完需要保存。\n• 基站信息是生成的模拟数据，不能对应到真实基站位置。\n• 不会断开手机网络，也不会改变实际 SIM 卡或公网 IP。",
              "• Editing one value may cause mismatches; refreshing the set aligns them again.\n• SIM, carrier and cell information apply together in SIM mode.\n• Wi-Fi and Bluetooth have individual settings; Off restores their real values too.\n• Switching modes preserves values. Save to apply changes.\n• Generated cell information does not identify a real tower location.\n• Your connection, physical SIM and public IP remain unchanged."));
    }
    private void refreshGroup(String group){
        String hint=group.equals("network")?t("重新生成网络、SIM 卡和基站参数，让运营商信息相互匹配。","Generate new network, SIM and cell values with matching carrier information."):
            t("重新生成 IMEI、序列号等设备标识，两条 IMEI 分别生成。","Generate new IMEIs, serial number and other device IDs. Each IMEI is distinct.");
        new AlertDialog.Builder(this).setTitle(t("刷新"+DeviceField.groupName(group,true)+"？","Refresh "+DeviceField.groupName(group,false)+"?"))
            .setMessage(hint+t("\n\n• 覆盖本分类的现有数值，并选中这些项目。\n• 其他分类和总开关保持原样。\n• 点击底部“保存机器伪装”后生效。",
                "\n\n• Replaces and selects this category's values.\n• Other categories and master switches stay as they are.\n• Tap Save device profile to apply."))
            .setNegativeButton(t("取消","Cancel"),null).setPositiveButton(t("刷新","Refresh"),(d,w)->{
                Map<String,String> packet=DevicePackets.group(group,preset);
                values.putAll(packet);selected.addAll(packet.keySet());renderContent();dirty();
            }).show();
    }
    private void chooseRegion(){
        final ChinaRegions data;
        try{data=regions();}catch(java.io.IOException e){
            Toast.makeText(this,t("地区数据无法读取","Region data unavailable"),Toast.LENGTH_LONG).show();return;
        }
        LinearLayout content=column();content.setPadding(dp(22),dp(10),dp(22),0);
        Spinner province=new Spinner(this),city=new Spinner(this),district=new Spinner(this);
        Spinner[] spinners={province,city,district};
        String[] labels={t("省 / 直辖市 / 自治区","Province"),t("市 / 地区","City"),t("区 / 县","District")};
        for(int i=0;i<spinners.length;i++){
            content.addView(text(labels[i],14,0xff475569));spinners[i].setContentDescription("device-region:"+i);
            content.addView(spinners[i],new LinearLayout.LayoutParams(-1,dp(48)));
        }
        TextView hint=text("",13,0xff667085);hint.setContentDescription("device-region-preview");content.addView(hint);
        content.addView(text(t("选好地区后，点击“应用到草稿”填写经纬度和精度。\n返回页面后可继续编辑，开启位置伪装并保存后生效。",
            "Choose a region, then tap Apply to draft to fill coordinates and accuracy.\nYou can edit them afterwards. Enable location spoofing and save to apply."),13,0xff667085));
        java.util.function.BiConsumer<Spinner,List<ChinaRegions.Region>> fill=(spinner,list)->{
            ArrayAdapter<ChinaRegions.Region> adapter=new ArrayAdapter<>(this,android.R.layout.simple_spinner_item,list);
            adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);spinner.setAdapter(adapter);
            for(int i=0;i<list.size();i++)if(regionId.startsWith(list.get(i).id)){spinner.setSelection(i);break;}
        };
        province.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){
            public void onNothingSelected(AdapterView<?> p){}
            public void onItemSelected(AdapterView<?> p,View v,int pos,long id){
                fill.accept(city,data.children(((ChinaRegions.Region)province.getSelectedItem()).id));
            }
        });
        city.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){
            public void onNothingSelected(AdapterView<?> p){}
            public void onItemSelected(AdapterView<?> p,View v,int pos,long id){
                fill.accept(district,data.children(((ChinaRegions.Region)city.getSelectedItem()).id));
            }
        });
        district.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){
            public void onNothingSelected(AdapterView<?> p){hint.setText(t("没有区县数据，可手工填写","District data unavailable; use manual fields"));}
            public void onItemSelected(AdapterView<?> p,View v,int pos,long id){
                ChinaRegions.Region r=(ChinaRegions.Region)district.getSelectedItem();
                hint.setText(r.hasPoint()?data.path(r)+"\n"+r.latitude+", "+r.longitude:
                    t("此区县缺少坐标，无法统一填写。可取消后手工填写。","Coordinates unavailable for this district. Cancel to enter values manually."));
            }
        });
        fill.accept(province,data.children("0"));
        ScrollView scroll=new ScrollView(this);scroll.addView(content);
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle(t("选择中国境内地区","Choose a region in China")).setView(scroll)
            .setNegativeButton(t("取消","Cancel"),null).setPositiveButton(t("应用到草稿","Apply to draft"),null).create();
        dialog.setOnShowListener(v->dialog.getButton(DialogInterface.BUTTON_POSITIVE).setOnClickListener(b->{
            ChinaRegions.Region r=(ChinaRegions.Region)district.getSelectedItem();
            if(r==null||!r.hasPoint()){hint.setText(t("缺少区县坐标，请选择其他地区或取消后手工填写。",
                "District coordinates unavailable. Choose another region or cancel to enter manually."));return;}
            Map<String,String> packet=data.packet(r);values.putAll(packet);selected.addAll(packet.keySet());
            regionId=r.id;regionName=data.path(r);regionOverrides.clear();renderContent();dirty();dialog.dismiss();
        }));dialog.show();
    }
    private void edit(DeviceField f) {
        LinearLayout content=column();content.setPadding(dp(22),dp(10),dp(22),0);
        Switch use=new Switch(this);use.setText(t("伪装这个字段","Spoof this field"));use.setChecked(selected.contains(f.id));
        if(DevicePackets.CELLULAR.contains(f.id)&&DeviceProfile.NETWORK_SIMULATE.equals(networkMode)){
            use.setChecked(true);use.setEnabled(false);
        }
        use.setContentDescription("device-use:"+f.id);content.addView(use);
        content.addView(text(f.hint,13,0xff667085));
        EditText input=new EditText(this);input.setText(values.getOrDefault(f.id,""));input.setSingleLine(true);
        input.setContentDescription("device-input:"+f.id);input.setEnabled(use.isChecked());content.addView(input);
        use.setOnCheckedChangeListener((b,on)->input.setEnabled(on));
        if(f.random)content.addView(button(t("生成新的随机值","Generate new value"),"device-dialog-random",()->{
            use.setChecked(true);input.setText(f.generate());
        }));
        if(f.group.equals("location")){
            Button restore=button(t("按所选地区还原此项","Restore this region value"),"device-dialog-region",()->{
                try{
                    ChinaRegions.Region r=regions().find(regionId);
                    if(r!=null&&r.hasPoint()){use.setChecked(true);input.setText(regions().packet(r).get(f.id));}
                }catch(java.io.IOException ignored){}
            });restore.setEnabled(!regionId.isEmpty());content.addView(restore);
        }else content.addView(button(t("从机型预设填入","Use a model preset value"),"device-dialog-preset",()->
            new AlertDialog.Builder(this).setTitle(t("仅替换此字段","Replace this field only"))
                .setItems(new String[]{t("小米 14 · 国际版","Xiaomi 14 · global"),"vivo X200 Pro mini"},
                    (d,w)->{
                        String value=DeviceProfile.preset(w==0?"xiaomi-14":"vivo-x200-pro-mini").values.get(f.id);
                        if(value==null){Toast.makeText(this,t("这个预设尚未核实此项，请手工填写","This value is not verified; enter it manually"),Toast.LENGTH_LONG).show();return;}
                        use.setChecked(true);input.setText(value);
                    }).show()));
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle(t(f.zh,f.en)).setView(content)
            .setNegativeButton(t("取消","Cancel"),null).setPositiveButton(t("更新草稿","Update draft"),null).create();
        dialog.setOnShowListener(v->dialog.getButton(DialogInterface.BUTTON_POSITIVE).setOnClickListener(b->{
            String value=input.getText().toString().trim(),error=f.validate(value);
            if(use.isChecked()&&error!=null){input.setError(error);return;}
            if(error==null){
                if(!value.equals(values.get(f.id)))markOverride(f);
                values.put(f.id,value);
                if(f.group.equals("location")&&!regionId.isEmpty())try{
                    ChinaRegions.Region r=regions().find(regionId);
                    if(r!=null&&r.hasPoint()&&value.equals(regions().packet(r).get(f.id)))regionOverrides.remove(f.id);
                }catch(java.io.IOException ignored){}
            }
            if(use.isChecked())selected.add(f.id);else selected.remove(f.id);
            renderContent();dirty();dialog.dismiss();
        }));dialog.show();
    }
    private void updateStatus() {
        if(status!=null)status.setText(t("已选择 ","Selected ")+selected.size()+"/"+DeviceField.ALL.size()+
            t(" 个字段 · 机型与系统"+(modelEnabled?"已开启":"已关闭")," fields · model "+(modelEnabled?"on":"off"))+
            t(" · 位置"+(locationEnabled?"已开启":"已关闭")," · location "+(locationEnabled?"on":"off")));
        if(consistencyHint!=null){
            List<String> warnings=ProfileWarnings.messages(draft(),Build.VERSION.RELEASE,zh);
            consistencyHint.setText(String.join("\n",warnings));
            consistencyHint.setVisibility(warnings.isEmpty()?View.GONE:View.VISIBLE);
        }
    }
    private boolean changed() { return !draft().json().equals(original.json()); }
    private void dirty() {
        updateStatus();
        if(saveHint!=null)saveHint.setText(changed()?t("草稿尚未保存","Draft has unsaved changes"):t("已保存；重复读取可跟随更新","Saved; repeated reads can follow updates"));
    }
    private void save() {
        if(store.save(pkg,draft())) {
            original=store.read(pkg);Toast.makeText(this,t("已保存。请查看检测页；缓存值需重新打开应用。",
                "Saved. Check actual reads in the verifier; cached values may need a restart."),Toast.LENGTH_LONG).show();finish();
        } else Toast.makeText(this,t("保存失败，请检查已选字段并重试","Save failed. Check selected fields and retry."),Toast.LENGTH_LONG).show();
    }
    private void back() {
        if(!changed()){finish();return;}
        new AlertDialog.Builder(this).setTitle(t("修改尚未保存","Unsaved changes")).setMessage(t("离开将丢弃草稿。","Leaving discards the draft."))
            .setNegativeButton(t("继续编辑","Keep editing"),null).setPositiveButton(t("丢弃","Discard"),(d,w)->finish()).show();
    }
    @android.annotation.SuppressLint("GestureBackNavigation")
    @Override public void onBackPressed(){back();}
    @Override protected void onSaveInstanceState(Bundle out) {
        out.putString("draft",draft().json());out.putString("original",original.json());out.putString("query",query);
        out.putStringArrayList("expanded",new ArrayList<>(expanded));super.onSaveInstanceState(out);
    }
}
