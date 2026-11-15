package io.github.lwtdzh.screenshotdetector;

import android.content.Context;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Debug;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.system.ErrnoException;
import android.system.Os;
import android.system.OsConstants;
import android.util.AtomicFile;
import android.util.Log;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.cert.Certificate;
import java.security.cert.X509Certificate;
import java.security.spec.ECGenParameterSpec;
import java.util.*;

/** Local observations only. No su execution, network requests, system writes or identity attestation. */
public final class EnvironmentProbe {
    private static final String OID = "1.3.6.1.4.1.11129.2.1.17";
    private static final String ALIAS_PREFIX = "appstate-environment-";
    private static native String nativeRead();
    private final Context context;
    private final boolean zh;
    private final JSONArray checks = new JSONArray();
    private final JSONObject evidence = new JSONObject();
    private EnvironmentProbe(Context context) {
        this.context = context.getApplicationContext();
        zh = context.getResources().getConfiguration().getLocales().get(0).getLanguage().equals("zh");
    }
    private String t(String cn, String en) { return zh ? cn : en; }
    private void add(String id, String cn, String en, String status, String value, String detail) throws Exception {
        checks.put(new JSONObject().put("id", id).put("label", t(cn, en)).put("status", status)
            .put("value", value).put("detail", detail));
    }
    private String unknown(Throwable error) {
        // Do not log raw provider errors, certificates, IDs or keystore aliases.
        return error.getClass().getSimpleName();
    }
    public static synchronized JSONObject run(Context context) {
        EnvironmentProbe probe = new EnvironmentProbe(context);
        return probe.collect();
    }
    private JSONObject collect() {
        JSONObject result = new JSONObject();
        try {
            result.put("schema", 1).put("version", BuildConfig.VERSION_NAME)
                .put("timestamp", System.currentTimeMillis()).put("pid", android.os.Process.myPid())
                .put("module", ModuleStatus.json()).put("checks", checks).put("evidence", evidence)
                .put("scope", "Local app observations; no remote integrity or online revocation check");
            JSONObject nativeValues = null;
            try {
                System.loadLibrary("environmentprobe");
                nativeValues = new JSONObject(nativeRead());
                evidence.put("native", nativeValues);
            } catch (Exception | LinkageError error) {
                add("native", "原生检查", "Native checks", "UNKNOWN", unknown(error),
                    t("原生读取失败；相关检查无法确认。", "Native reads failed; affected checks are unknown."));
            }
            rootFiles(nativeValues);
            injection(nativeValues);
            properties(nativeValues);
            ordinary(nativeValues);
            try {
                JSONObject modules = ModuleListProbe.read(context);
                evidence.put("moduleList", modules);
                JSONArray apps = modules.optJSONArray("applications");
                int count = apps == null ? 0 : apps.length();
                add("modules", "可见 Xposed 模块", "Visible Xposed modules",
                    modules.has("error") ? "UNKNOWN" : count > 0 ? "WARN" : "PASS",
                    modules.has("error") ? modules.optString("error") : String.valueOf(count),
                    t("仅检查当前应用可查询的模块元数据；空列表不证明未安装框架。",
                        "Only visible module metadata is queried; an empty list does not prove no framework is installed."));
            } catch (Exception error) {
                add("modules", "可见 Xposed 模块", "Visible Xposed modules", "UNKNOWN", unknown(error), "");
            }
            try {
                context.getClassLoader().loadClass("de.robv.android.xposed.XposedBridge");
                add("xposedClass", "Xposed Java 类", "Xposed Java class", "WARN", "visible",
                    t("类可见是注入线索；不检测 ART 方法 Hook。",
                        "A visible class is an injection signal; this does not scan ART method hooks."));
            } catch (ClassNotFoundException expected) {
                add("xposedClass", "Xposed Java 类", "Xposed Java class", "PASS", "not found",
                    t("本次类查询未发现；不代表没有其他注入方式。", "Not found by this class lookup; other injection methods may exist."));
            } catch (Exception | LinkageError error) {
                add("xposedClass", "Xposed Java 类", "Xposed Java class", "UNKNOWN", unknown(error), "");
            }
            PackageManager pm = context.getPackageManager();
            add("idAttestation", "设备 ID 证明能力", "Device ID attestation feature", "INFO",
                String.valueOf(pm.hasSystemFeature("android.software.device_id_attestation")),
                t("只读功能标记，不请求 IMEI、序列号等身份字段。",
                    "Reads the feature flag only; IMEI, serial and other identity fields are never requested."));
            add("strongboxFeature", "StrongBox 能力标记", "StrongBox feature", "INFO",
                String.valueOf(pm.hasSystemFeature(PackageManager.FEATURE_STRONGBOX_KEYSTORE)),
                t("默认生成普通 EC 证明密钥；未主动申请 StrongBox 密钥。",
                    "The probe generates a regular EC attestation key; it does not explicitly request StrongBox."));
            attestation();
        } catch (Exception error) {
            try { add("probe", "检查未完成", "Incomplete probe", "UNKNOWN", unknown(error), ""); }
            catch (Exception ignored) {}
        }
        try {
            int pass = 0, warn = 0, unconfirmed = 0, info = 0;
            for (int i = 0; i < checks.length(); i++) {
                JSONObject check = checks.getJSONObject(i);
                switch (check.getString("status")) {
                    case "PASS": pass++; break;
                    case "WARN": warn++; break;
                    case "UNKNOWN": unconfirmed++; break;
                    default: info++;
                }
                Log.i("EnvironmentProbe", check.getString("id") + " " + check.getString("status")
                    + " " + check.getString("value"));
            }
            result.put("summary", new JSONObject().put("pass", pass).put("warn", warn)
                .put("unknown", unconfirmed).put("info", info));
            AtomicFile file = new AtomicFile(new File(context.getFilesDir(), "environment-result.json"));
            FileOutputStream out = null;
            try {
                out = file.startWrite();
                out.write(result.toString(2).getBytes(StandardCharsets.UTF_8));
                file.finishWrite(out);
            } catch (IOException error) {
                file.failWrite(out);
                Log.w("EnvironmentProbe", "Private result write failed: " + unknown(error));
            }
        } catch (Exception error) { Log.w("EnvironmentProbe", "Result formatting failed: " + unknown(error)); }
        return result;
    }
    private void rootFiles(JSONObject nativeValues) throws Exception {
        String[] paths = {"/system/bin/su", "/system/xbin/su", "/sbin/su", "/su/bin/su",
            "/system/bin/busybox", "/system/xbin/busybox", "/data/adb/magisk",
            "/data/adb/ksu", "/data/adb/modules", "/sbin/.magisk"};
        JSONArray javaFiles = new JSONArray(), nativeFiles = nativeValues == null ? null : nativeValues.optJSONArray("files");
        List<String> found = new ArrayList<>(), denied = new ArrayList<>();
        for (int i = 0; i < paths.length; i++) {
            String javaRead;
            try { Os.stat(paths[i]); javaRead = "present"; }
            catch (ErrnoException error) {
                javaRead = error.errno == OsConstants.ENOENT || error.errno == OsConstants.ENOTDIR
                    ? "absent" : "unknown:errno=" + error.errno;
            } catch (SecurityException error) { javaRead = "unknown:SecurityException"; }
            javaFiles.put(new JSONObject().put("path", paths[i]).put("value", javaRead));
            JSONObject item = nativeFiles == null ? null : nativeFiles.optJSONObject(i);
            String libc = item == null ? "unknown:unavailable" : item.optString("libc"),
                syscall = item == null ? "unknown:unavailable" : item.optString("syscall");
            if ("present".equals(javaRead) || "present".equals(libc) || "present".equals(syscall)) found.add(paths[i]);
            else if (javaRead.startsWith("unknown") || libc.startsWith("unknown") || syscall.startsWith("unknown"))
                denied.add(paths[i]);
        }
        evidence.put("javaFiles", javaFiles);
        add("rootFiles", "Su / Busybox / Root 文件", "Su / Busybox / Root files",
            !found.isEmpty() ? "WARN" : !denied.isEmpty() ? "UNKNOWN" : "PASS",
            !found.isEmpty() ? String.join(", ", found) : !denied.isEmpty() ? t("部分路径不可读", "Some paths are inaccessible") : "not found",
            t("Java、libc stat 和直接 faccessat syscall 对照。权限拒绝不能证明文件不存在；不执行 su。",
                "Compares Java, libc stat and direct faccessat syscall. Permission denial cannot prove absence; su is not executed.")
                + (denied.isEmpty() ? "" : "\n" + String.join(", ", denied)));
    }
    private void injection(JSONObject values) throws Exception {
        for (String source : new String[]{"maps", "linker"}) {
            JSONArray paths = values == null ? null : values.optJSONArray(source);
            boolean unavailable = paths == null || ("maps".equals(source) &&
                (values.optInt("mapsError") != 0 || values.optBoolean("mapsTruncated")));
            LinkedHashSet<String> unique = new LinkedHashSet<>();
            if (paths != null) for (int i = 0; i < paths.length(); i++) unique.add(paths.getString(i));
            add("injection." + source, "注入库 · " + source, "Injected libraries · " + source,
                !unique.isEmpty() ? "WARN" : unavailable ? "UNKNOWN" : "PASS",
                unique.isEmpty() ? unavailable ? t("无法完整读取", "Incomplete read") : "not found" : String.join("\n", unique),
                t("只匹配已知框架库路径；不等同于 Native Detector 的全部扫描算法，也不检测隐藏/匿名映射。",
                    "Matches known framework paths only; this is not Native Detector's full algorithm and does not detect hidden or anonymous mappings."));
        }
    }
    private void properties(JSONObject values) throws Exception {
        JSONObject props = values == null ? null : values.optJSONObject("properties");
        for (String key : new String[]{"ro.build.tags", "ro.build.type", "ro.debuggable", "ro.secure",
            "ro.vendor_dlkm.build.tags", "ro.odm_dlkm.build.tags", "ro.system_dlkm.build.tags",
            "ro.boot.verifiedbootstate", "ro.boot.flash.locked", "ro.boot.vbmeta.device_state", "ro.boot.veritymode"}) {
            String value = props == null ? "" : props.optString(key);
            boolean warning = value.contains("test-keys") || value.contains("dev-keys") || value.equals("userdebug") ||
                value.equals("eng") || (key.equals("ro.debuggable") && value.equals("1")) ||
                (key.equals("ro.secure") && value.equals("0")) || value.equals("orange") ||
                value.equals("red") || value.equals("unlocked") || (key.equals("ro.boot.flash.locked") && value.equals("0"));
            boolean boot = key.startsWith("ro.boot.");
            add("property." + key, key, key, value.isEmpty() ? "UNKNOWN" : warning ? "WARN" : boot ? "INFO" : "PASS",
                value.isEmpty() ? t("缺失或不可读", "Missing or inaccessible") : value,
                t("原生属性读数可受 Hook 影响；启动属性只作参考，应核对签名证明。",
                    "Native properties can be hooked; boot properties are informational and should be compared with signed attestation."));
        }
        add("buildTags", "Java Build.TAGS", "Java Build.TAGS",
            Build.TAGS == null ? "UNKNOWN" : Build.TAGS.contains("test-keys") || Build.TAGS.contains("dev-keys") ? "WARN" : "PASS",
            String.valueOf(Build.TAGS), t("Java 构建字段也可受机型伪装影响。", "Java build fields can also be spoofed."));
    }
    private void ordinary(JSONObject nativeValues) throws Exception {
        Map<String, Integer> state = ObservedState.read(context);
        String[] keys = {"vpn", "proxy", "developer", "usb", "wireless", "selinux"};
        String[] cn = {"VPN", "网络代理", "开发者选项", "USB 调试", "无线调试", "SELinux · Java"};
        String[] en = {"VPN", "Network proxy", "Developer options", "USB debugging", "Wireless debugging", "SELinux · Java"};
        for (int i = 0; i < keys.length; i++) {
            int value = state.get(keys[i]);
            boolean unknown = value == R.string.summary_unknown || value == R.string.summary_selinux_unconfirmed;
            boolean on = value == R.string.summary_on || value == R.string.summary_configured ||
                value == R.string.summary_permissive || ("selinux".equals(keys[i]) && value == R.string.summary_off);
            add(keys[i], cn[i], en[i], unknown ? "UNKNOWN" : on ? "WARN" : "PASS", context.getString(value),
                t("当前应用实际读取；开启状态是可见信号，不能单独证明 Root。",
                    "Actual app read; an enabled state is a visible signal and cannot prove root by itself."));
        }
        String enforce = nativeValues == null ? "unknown:unavailable" : nativeValues.optString("selinux");
        add("selinux.native", "SELinux · 原生文件", "SELinux · native file",
            enforce.startsWith("unknown") ? "UNKNOWN" : enforce.equals("Enforcing") ? "PASS" : "WARN", enforce,
            t("只读 enforce 文件，不修改系统状态。", "Reads the enforce file without changing system state."));
        add("debugger", "当前进程调试器", "Current process debugger",
            Debug.isDebuggerConnected() ? "WARN" : "PASS", String.valueOf(Debug.isDebuggerConnected()),
            t("读取 Android Debug API；不检测全部 ptrace/内核追踪方式。",
                "Reads the Android Debug API; not all ptrace or kernel tracing methods are detected."));
    }
    private void attestation() throws Exception {
        String alias = ALIAS_PREFIX + UUID.randomUUID();
        KeyStore store = null;
        boolean generated = false;
        try {
            byte[] challenge = new byte[32]; new SecureRandom().nextBytes(challenge);
            store = KeyStore.getInstance("AndroidKeyStore"); store.load(null);
            KeyPairGenerator generator = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore");
            generator.initialize(new KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_SIGN)
                .setAlgorithmParameterSpec(new ECGenParameterSpec("secp256r1"))
                .setDigests(KeyProperties.DIGEST_SHA256).setAttestationChallenge(challenge).build());
            generator.generateKeyPair(); generated = true;
            Certificate[] raw = store.getCertificateChain(alias);
            if (raw == null || raw.length == 0 || raw.length > 16) throw new GeneralSecurityException();
            List<X509Certificate> chain = new ArrayList<>();
            for (Certificate certificate : raw) chain.add((X509Certificate) certificate);
            boolean signaturesValid = true;
            try {
                for (int i = 0; i < chain.size(); i++) {
                    X509Certificate cert = chain.get(i); cert.checkValidity();
                    X509Certificate issuer = chain.get(Math.min(i + 1, chain.size() - 1));
                    if (!cert.getIssuerX500Principal().equals(issuer.getSubjectX500Principal()))
                        throw new GeneralSecurityException();
                    cert.verify(issuer.getPublicKey());
                }
            } catch (GeneralSecurityException error) { signaturesValid = false; }
            add("attestation.chain", "证明链签名与有效期", "Attestation chain signatures and dates",
                signaturesValid ? "PASS" : "WARN", String.valueOf(signaturesValid),
                t("离线逐级检查签名、签发者和有效期；尚未核对在线吊销列表或完整 PKIX 策略。",
                    "Offline signatures, issuer names and validity dates; online revocation and full PKIX policy are not checked."));
            X509Certificate root = chain.get(chain.size() - 1);
            String fingerprint = hex(MessageDigest.getInstance("SHA-256").digest(root.getPublicKey().getEncoded()));
            String anchor = null;
            try (InputStream input = context.getAssets().open("attestation-trust-anchors.json")) {
                JSONArray anchors = new JSONObject(new String(readBounded(input), StandardCharsets.UTF_8)).getJSONArray("anchors");
                for (int i = 0; i < anchors.length(); i++)
                    if (fingerprint.equals(anchors.getJSONObject(i).getString("spkiSha256")))
                        anchor = anchors.getJSONObject(i).getString("name");
            }
            evidence.put("attestation", new JSONObject().put("certificateCount", chain.size())
                .put("rootSpkiSha256", fingerprint).put("rootSubject", root.getSubjectX500Principal().getName()));
            add("attestation.root", "Google 证明根匹配", "Google attestation root match",
                anchor == null ? "UNKNOWN" : signaturesValid ? "PASS" : "WARN",
                anchor == null ? t("未匹配已收录的 Google 根", "No match in bundled Google roots") : anchor,
                t("未知根可能是厂商根或测试根；不能据此单独判定 Root。公钥指纹清单：2026-11-15。",
                    "An unknown root may be a vendor or test root; this alone cannot establish root. Pins dated 2026-11-15."));
            // Official guidance: use the first extension encountered walking from root toward leaf.
            byte[] extension = null;
            for (int i = chain.size() - 1; i >= 0; i--)
                if ((extension = chain.get(i).getExtensionValue(OID)) != null) break;
            if (extension == null) throw new GeneralSecurityException("Attestation extension unavailable");
            AttestationRecord record = AttestationRecord.parse(extension);
            boolean challengeValid = MessageDigest.isEqual(record.challenge, challenge);
            add("attestation.challenge", "新生成证明的 Challenge", "Fresh attestation challenge",
                challengeValid ? "PASS" : "WARN", String.valueOf(challengeValid),
                t("每次使用新的随机挑战，避免读取旧证明；挑战内容不写入日志。",
                    "A new random challenge is used on each run; challenge bytes are not logged."));
            String warning = t("这是本地解析结果。未知根或无效链时，字段不能作为已受信任的事实。",
                "Locally parsed fields; an unknown root or invalid chain means they are not authenticated facts.");
            add("attestation.security", "证明安全级别", "Attestation security level",
                record.attestationSecurity == 0 ? "WARN" : "INFO", AttestationRecord.security(record.attestationSecurity), warning);
            add("attestation.keyMint", "Keymaster / KeyMint 安全级别", "Keymaster / KeyMint security level",
                record.keyMintSecurity == 0 ? "WARN" : "INFO", AttestationRecord.security(record.keyMintSecurity), warning);
            AttestationRecord.RootOfTrust boot = record.root;
            if (boot == null) {
                for (String field : new String[]{"locked", "state", "key", "hash"})
                    add("attestation.boot." + field, "启动证明 · " + field, "Boot attestation · " + field,
                        "UNKNOWN", t("证明未提供", "Not supplied"), warning);
            } else {
                add("attestation.boot.locked", "证明 deviceLocked", "Attested deviceLocked",
                    boot.locked ? "INFO" : "WARN", String.valueOf(boot.locked), warning);
                add("attestation.boot.state", "证明 verifiedBootState", "Attested verifiedBootState",
                    boot.state == 0 ? "INFO" : "WARN", AttestationRecord.bootState(boot.state), warning);
                bootBytes("key", "verifiedBootKey", boot.key, warning);
                bootBytes("hash", "verifiedBootHash", boot.hash, warning);
            }
            add("attestation.revocation", "证明吊销状态", "Attestation revocation status", "UNKNOWN",
                t("未在线核验", "Not checked online"),
                t("检测器不联网、不调用 Play Integrity；本地 Hook 仍可能影响读取。",
                    "No network or Play Integrity calls; local hooks may still affect observations."));
        } catch (Exception | LinkageError error) {
            add("attestation.available", "密钥证明检查", "Key attestation check", "UNKNOWN", unknown(error),
                t("密钥服务不支持、证书缺失或读取失败时无法确认；不会改为伪造证明。",
                    "Unavailable for unsupported keystores, missing certificates or read failures."));
        } finally {
            boolean cleaned = !generated;
            if (store != null) {
                try {
                    // Never enumerate or delete other applications' existing aliases.
                    if (store.containsAlias(alias)) store.deleteEntry(alias);
                    cleaned = !store.containsAlias(alias);
                } catch (GeneralSecurityException error) { cleaned = false; }
            }
            add("attestation.cleanup", "临时证明密钥清理", "Temporary attestation key cleanup",
                cleaned ? "PASS" : "WARN", String.valueOf(cleaned),
                t("仅删除本次随机别名；不导出私钥、证书或设备 ID。", "Deletes this run's random alias only; no keys, certificates or device IDs are exported."));
        }
    }
    private void bootBytes(String id, String label, byte[] bytes, String detail) throws Exception {
        add("attestation.boot." + id, "证明 " + label, "Attested " + label,
            bytes == null || bytes.length == 0 ? "UNKNOWN" : AttestationRecord.allZero(bytes) ? "WARN" : "INFO",
            bytes == null || bytes.length == 0 ? t("未提供", "Not supplied") : AttestationRecord.allZero(bytes)
                ? t("全零", "All zero") : t("非零，长度 ", "Nonzero, bytes: ") + bytes.length,
            detail + t(" 非零也不能单独证明生产启动链。", " A nonzero value alone cannot prove a production boot chain."));
    }
    private static byte[] readBounded(InputStream input) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buffer = new byte[4096]; int count;
        while ((count = input.read(buffer)) != -1) {
            if (out.size() + count > 65536) throw new IOException();
            out.write(buffer, 0, count);
        }
        return out.toByteArray();
    }
    private static String hex(byte[] bytes) {
        StringBuilder value = new StringBuilder();
        for (byte b : bytes) value.append(String.format(Locale.ROOT, "%02x", b & 255));
        return value.toString();
    }
}
