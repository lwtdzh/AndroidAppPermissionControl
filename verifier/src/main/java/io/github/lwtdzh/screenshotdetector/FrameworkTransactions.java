package io.github.lwtdzh.screenshotdetector;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

/** Reads generated AIDL constants from installed framework Dex, without hidden-API changes. */
public final class FrameworkTransactions {
    public static int[] capture() throws Exception {
        try {
            Class<?> stub = Class.forName("android.app.IActivityTaskManager$Stub");
            java.lang.reflect.Field r = stub.getDeclaredField("TRANSACTION_registerScreenCaptureObserver");
            java.lang.reflect.Field u = stub.getDeclaredField("TRANSACTION_unregisterScreenCaptureObserver");
            r.setAccessible(true); u.setAccessible(true);
            return new int[]{r.getInt(null), u.getInt(null)};
        } catch (ReflectiveOperationException | RuntimeException ignored) {
            try (ZipFile jar = new ZipFile("/system/framework/framework.jar")) {
                for (int i = 1; i <= 16; i++) {
                    ZipEntry entry = jar.getEntry(i == 1 ? "classes.dex" : "classes" + i + ".dex");
                    if (entry == null) break;
                    if (entry.getSize() > 80_000_000) continue;
                    byte[] bytes;
                    try (java.io.InputStream input = jar.getInputStream(entry);
                         java.io.ByteArrayOutputStream output = new java.io.ByteArrayOutputStream()) {
                        byte[] buffer = new byte[8192]; int n;
                        while ((n = input.read(buffer)) != -1) {
                            if (output.size() + n > 80_000_000) throw new IllegalArgumentException("Oversized Dex");
                            output.write(buffer, 0, n);
                        }
                        bytes = output.toByteArray();
                    }
                    int[] result = new FrameworkTransactions(bytes).find();
                    if (result != null) return result;
                }
            }
        }
        throw new UnsupportedOperationException("AIDL constants unavailable");
    }
    private final ByteBuffer data;
    private final int strings, types, fields;
    private FrameworkTransactions(byte[] bytes) {
        if (bytes.length < 112 || bytes[0] != 'd' || bytes[1] != 'e' || bytes[2] != 'x')
            throw new IllegalArgumentException("Not dex");
        data = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN);
        strings = data.getInt(60); types = data.getInt(68); fields = data.getInt(84);
    }
    private int uleb() {
        int value = 0;
        for (int shift = 0; shift < 35; shift += 7) {
            int b = data.get() & 255;
            value |= (b & 127) << shift;
            if ((b & 128) == 0) return value;
        }
        throw new IllegalArgumentException("Invalid uleb");
    }
    private String string(int index) {
        int position = data.position();
        data.position(data.getInt(strings + index * 4));
        uleb();
        int begin = data.position(), end = begin;
        while (data.get(end) != 0) end++;
        String result = new String(data.array(), begin, end - begin, StandardCharsets.UTF_8);
        data.position(position);
        return result;
    }
    private int[] find() {
        int count = data.getInt(96), offset = data.getInt(100);
        for (int i = 0; i < count; i++) {
            int c = offset + i * 32, type = data.getInt(c);
            if (!string(data.getInt(types + type * 4)).equals("Landroid/app/IActivityTaskManager$Stub;")) continue;
            int classData = data.getInt(c + 24), values = data.getInt(c + 28);
            if (classData == 0 || values == 0) return null;
            data.position(classData);
            int staticCount = uleb(); uleb(); uleb(); uleb();
            String[] names = new String[staticCount];
            int field = 0;
            for (int j = 0; j < staticCount; j++) {
                field += uleb(); uleb();
                names[j] = string(data.getInt(fields + field * 8 + 4));
            }
            data.position(values);
            int valueCount = uleb(), register = -1, unregister = -1;
            for (int j = 0; j < valueCount; j++) {
                int header = data.get() & 255, kind = header & 31, width = (header >> 5) + 1, value = 0;
                if (kind == 0x1e || kind == 0x1f) continue;
                if (kind == 0x1c || kind == 0x1d) throw new UnsupportedOperationException("Nested encoded value");
                for (int k = 0; k < width; k++) value |= (data.get() & 255) << (k * 8);
                if (j < names.length && kind == 4) {
                    if (names[j].equals("TRANSACTION_registerScreenCaptureObserver")) register = value;
                    if (names[j].equals("TRANSACTION_unregisterScreenCaptureObserver")) unregister = value;
                }
            }
            return register > 0 && unregister > 0 ? new int[]{register, unregister} : null;
        }
        return null;
    }
}
