package io.github.lwtdzh.screenshotdetector;

import android.app.Activity;
import android.os.Bundle;
import android.os.Handler;
import android.os.HandlerThread;
import android.content.Intent;
import android.security.keystore.*;
import android.widget.TextView;
import org.json.*;
import java.io.File;
import java.nio.file.Files;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.cert.*;
import java.security.spec.ECGenParameterSpec;
import java.util.Arrays;

/** Narrow new-code probe; never invokes phone/serial samplers. Debug builds only. */
public final class IncrementalProbeActivity extends Activity {
    private static native String nativeProbe(String model,String fingerprint,String path);
    private static native String nativeEdges(String model);
    private HandlerThread thread;
    private Handler worker;
    private TextView text;
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);text=new TextView(this);text.setText("Running new native and Keystore checks…");
        setContentView(text);
        thread=new HandlerThread("IncrementalExistingWorker");thread.start();
        worker=new Handler(thread.getLooper());runProbe();
    }
    @Override public void onNewIntent(Intent intent) {
        super.onNewIntent(intent);setIntent(intent);runProbe();
    }
    private void runProbe() {
        String model=getIntent().getStringExtra("model"),fingerprint=getIntent().getStringExtra("fingerprint");
        boolean keyProbe=getIntent().getBooleanExtra("keys",false);
        boolean modelOnly=getIntent().getBooleanExtra("modelOnly",false);
        boolean edges=getIntent().getBooleanExtra("edges",false);
        String androidId=getIntent().getStringExtra("androidId");
        long revision=getIntent().getLongExtra("revision",-1);
        worker.post(()-> {
            JSONObject result=new JSONObject();
            try {
                Bundle read=getContentResolver().call(android.net.Uri.parse(
                    "content://io.github.lwtdzh.appstateshield.policy"),"read",getPackageName(),null);
                long providerRevision=read==null?-1:new JSONObject(read.getString("device")).optLong("revision");
                long deadline=android.os.SystemClock.uptimeMillis()+12000;
                while(revision>=0 && ModuleStatus.snapshot().getLong("deviceRevision")!=revision &&
                        android.os.SystemClock.uptimeMillis()<deadline)Thread.sleep(50);
                if(revision>=0 && ModuleStatus.snapshot().getLong("deviceRevision")!=revision)
                    throw new IllegalStateException("Profile revision was not published; provider="+providerRevision+
                        " expected="+revision+" actual="+ModuleStatus.snapshot().getLong("deviceRevision"));
                if(edges) {
                    System.loadLibrary("incrementalprobe");
                    result=new JSONObject(nativeEdges(model));
                } else if(modelOnly) {
                    result.put("modelMatches",java.util.Objects.equals(model,android.os.Build.MODEL))
                        .put("fingerprintMatches",java.util.Objects.equals(fingerprint,android.os.Build.FINGERPRINT))
                        .put("androidIdMatches",java.util.Objects.equals(androidId,
                            android.provider.Settings.Secure.getString(getContentResolver(),"android_id")))
                        .put("simState",((android.telephony.TelephonyManager)getSystemService(TELEPHONY_SERVICE)).getSimState())
                        .put("oldNativeChecksSkipped",true);
                } else {
                    System.loadLibrary("incrementalprobe");
                    File control=new File(getFilesDir(),"incremental-control");
                    Files.write(control.toPath(),"ordinary-native-file-control-047".getBytes(StandardCharsets.UTF_8));
                    result=new JSONObject(nativeProbe(model,fingerprint,control.getAbsolutePath()));
                }
                if(keyProbe)result.put("keystore",keys());
                result.put("module",ModuleStatus.json());
                android.util.DisplayMetrics display=new android.util.DisplayMetrics();
                getWindowManager().getDefaultDisplay().getRealMetrics(display);
                result.put("display",new JSONObject().put("width",display.widthPixels)
                    .put("height",display.heightPixels).put("density",display.densityDpi));
                result.put("pid",android.os.Process.myPid()).put("workerTid",android.os.Process.myTid());
            }catch(Throwable error){try{result.put("error",error.toString()).put("module",ModuleStatus.json());}catch(Exception ignored){}}
            try {
                Files.write(new File(getFilesDir(),"incremental-result.json").toPath(),
                    result.toString(2).getBytes(StandardCharsets.UTF_8));
                runOnUiThread(()->text.setText("Incremental checks saved."));
            }catch(Exception ignored){}
        });
    }
    @Override public void onDestroy(){if(thread!=null)thread.quitSafely();super.onDestroy();}
    private JSONObject keys()throws Exception {
        String normal="appstate-incremental-normal",proof="appstate-incremental-proof";
        KeyStore store=KeyStore.getInstance("AndroidKeyStore");store.load(null);
        JSONObject result=new JSONObject();
        try {
            KeyPairGenerator generator=KeyPairGenerator.getInstance("EC","AndroidKeyStore");
            generator.initialize(new KeyGenParameterSpec.Builder(normal,KeyProperties.PURPOSE_SIGN|KeyProperties.PURPOSE_VERIFY)
                .setAlgorithmParameterSpec(new ECGenParameterSpec("secp256r1"))
                .setDigests(KeyProperties.DIGEST_SHA256).build());
            KeyPair pair=generator.generateKeyPair();
            byte[] message="ordinary-cryptographic-control".getBytes(StandardCharsets.UTF_8);
            Signature signer=Signature.getInstance("SHA256withECDSA");signer.initSign(pair.getPrivate());signer.update(message);
            byte[] signature=signer.sign();
            Signature verifier=Signature.getInstance("SHA256withECDSA");verifier.initVerify(pair.getPublic());verifier.update(message);
            result.put("ordinarySignVerify",verifier.verify(signature));
            result.put("normalCertificateKeyMatches",Arrays.equals(
                store.getCertificate(normal).getPublicKey().getEncoded(),pair.getPublic().getEncoded()));
            byte[] challenge="incremental-attestation-challenge".getBytes(StandardCharsets.UTF_8);
            try {
                generator.initialize(new KeyGenParameterSpec.Builder(proof,KeyProperties.PURPOSE_SIGN)
                    .setAlgorithmParameterSpec(new ECGenParameterSpec("secp256r1"))
                    .setDigests(KeyProperties.DIGEST_SHA256).setAttestationChallenge(challenge)
                    .setDevicePropertiesAttestationIncluded(true).build());
                generator.generateKeyPair();
                X509Certificate certificate=(X509Certificate)store.getCertificate(proof);
                byte[] extension=certificate.getExtensionValue("1.3.6.1.4.1.11129.2.1.17");
                result.put("attestationGenerated",true).put("challengePreserved",challenge(extension,challenge));
                java.security.cert.Certificate[] chain=store.getCertificateChain(proof);
                boolean signatures=true;
                for(int i=0;i+1<chain.length;i++) {
                    try{chain[i].verify(chain[i+1].getPublicKey());}catch(Exception error){signatures=false;}
                }
                result.put("chainSignaturesUnmodified",signatures).put("chainLength",chain.length);
                // A self-consistent emulator chain is not a trusted physical-device proof.
                result.put("trustedRootVerified",false);
            }catch(Exception error) {
                result.put("attestationGenerated",false).put("attestationError",error.getClass().getName());
                Throwable cause=error;while(cause.getCause()!=null)cause=cause.getCause();
                result.put("attestationCause",cause.getClass().getName());
                if(cause instanceof android.security.KeyStoreException)
                    result.put("attestationErrorCode",((android.security.KeyStoreException)cause).getNumericErrorCode());
            }
        }finally {
            if(store.containsAlias(normal))store.deleteEntry(normal);
            if(store.containsAlias(proof))store.deleteEntry(proof);
        }
        return result;
    }
    private static byte[] content(byte[] data,int[] offset,int wanted) {
        if(data==null || offset[0]+2>data.length || (data[offset[0]++]&255)!=wanted)return null;
        int length=data[offset[0]++]&255;
        if((length&128)!=0) {
            int count=length&127;if(count==0 || count>4 || offset[0]+count>data.length)return null;
            length=0;while(count-->0)length=(length<<8)|(data[offset[0]++]&255);
        }
        if(length<0 || length>data.length-offset[0])return null;
        byte[] result=Arrays.copyOfRange(data,offset[0],offset[0]+length);offset[0]+=length;return result;
    }
    private static boolean challenge(byte[] extension,byte[] expected) {
        byte[] wrapper=content(extension,new int[]{0},4);
        byte[] sequence=content(wrapper,new int[]{0},48);
        int[] at={0};
        if(sequence==null)return false;
        for(int i=0;i<4;i++)if(content(sequence,at,i%2==0?2:10)==null)return false;
        return Arrays.equals(expected,content(sequence,at,4));
    }
}
