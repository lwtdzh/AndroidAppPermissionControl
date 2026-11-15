package io.github.lwtdzh.screenshotdetector;

import android.app.Activity;
import android.os.Bundle;
import android.widget.TextView;
import org.json.JSONObject;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;

/** Debug-only capability research. Native irreversible probes run in a short-lived child. */
public final class CapabilityProbeActivity extends Activity {
    private static native String nativeProbe();
    @Override public void onCreate(Bundle state){
        super.onCreate(state);
        TextView label=new TextView(this);label.setText("Checking native capabilities…");setContentView(label);
        new Thread(()->{
            try {
                System.loadLibrary("capabilityprobe");
                JSONObject result=new JSONObject(nativeProbe());
                result.put("package",getPackageName()).put("uid",android.os.Process.myUid())
                    .put("pid",android.os.Process.myPid()).put("sdk",android.os.Build.VERSION.SDK_INT);
                File output=new File(getFilesDir(),"capability-result.json");
                Files.write(output.toPath(),result.toString(2).getBytes(StandardCharsets.UTF_8));
                runOnUiThread(()->label.setText("Native capability checks saved."));
            }catch(Throwable error){
                try {
                    Files.write(new File(getFilesDir(),"capability-result.json").toPath(),
                        new JSONObject().put("error",error.toString()).toString().getBytes(StandardCharsets.UTF_8));
                }catch(Exception ignored){}
                runOnUiThread(()->label.setText("Capability check failed: "+error.getClass().getSimpleName()));
            }
        },"CapabilityProbe").start();
    }
}
