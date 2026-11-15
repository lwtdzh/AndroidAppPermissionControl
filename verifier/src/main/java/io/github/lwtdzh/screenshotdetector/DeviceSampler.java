package io.github.lwtdzh.screenshotdetector;

import android.app.Activity;
import android.os.Handler;
import android.os.Looper;
import android.view.Display;
import org.json.JSONObject;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.Consumer;

/** Serial real reads shared by foreground pages; paused pages cannot publish stale results. */
final class DeviceSampler {
    private static final ExecutorService WORKER=Executors.newSingleThreadExecutor();
    private final Activity activity;
    private final Consumer<JSONObject> render;
    private final String filename;
    private final Handler main=new Handler(Looper.getMainLooper());
    private boolean active,busy;
    private int generation;
    DeviceSampler(Activity activity,String filename,Consumer<JSONObject> render){
        this.activity=activity;this.filename=filename;this.render=render;
    }
    private final Runnable tick=new Runnable(){
        @Override public void run(){
            if(!active)return;
            if(!busy){
                busy=true;int token=generation;
                Display display=activity.getWindowManager().getDefaultDisplay();
                WORKER.execute(()->{
                    JSONObject result=DeviceRead.read(activity.getApplicationContext(),display);
                    main.post(()->{
                        busy=false;
                        if(!active||token!=generation)return;
                        // Private diagnostic evidence only, also used by local ADB tests.
                        try{
                            java.io.File target=new java.io.File(activity.getFilesDir(),filename);
                            java.io.File next=new java.io.File(activity.getFilesDir(),filename+".next");
                            try(java.io.FileOutputStream out=new java.io.FileOutputStream(next)){
                                out.write(result.toString(2).getBytes(java.nio.charset.StandardCharsets.UTF_8));
                            }
                            if(!next.renameTo(target))next.delete();
                        }catch(Exception ignored){}
                        render.accept(result);
                    });
                });
            }
            main.postDelayed(this,2000);
        }
    };
    void start(){if(active)return;active=true;generation++;main.removeCallbacks(tick);main.post(tick);}
    void stop(){active=false;generation++;main.removeCallbacks(tick);}
}
