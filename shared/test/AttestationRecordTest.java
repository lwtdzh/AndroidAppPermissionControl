import io.github.lwtdzh.screenshotdetector.AttestationRecord;
import java.io.ByteArrayOutputStream;
import java.util.Arrays;
import java.util.Random;

public final class AttestationRecordTest {
    private static int assertions;
    private static void check(boolean value) { assertions++; if (!value) throw new AssertionError(); }
    private static byte[] join(byte[]... items) {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        for (byte[] item : items) out.writeBytes(item);
        return out.toByteArray();
    }
    private static byte[] tlv(byte[] tag, byte[] bytes) {
        byte[] length = bytes.length < 128 ? new byte[]{(byte) bytes.length} :
            bytes.length < 256 ? new byte[]{(byte) 0x81, (byte) bytes.length} :
                new byte[]{(byte) 0x82, (byte)(bytes.length >> 8), (byte)bytes.length};
        return join(tag, length, bytes);
    }
    private static byte[] value(int tag, byte... bytes) { return tlv(new byte[]{(byte)tag}, bytes); }
    private static byte[] sequence(byte[]... fields) { return value(0x30, join(fields)); }
    private static byte[] root(boolean hash) {
        byte[] fields = join(value(4, new byte[32]), value(1, (byte)0), value(10, (byte)2));
        if (hash) fields = join(fields, value(4, new byte[32]));
        return tlv(new byte[]{(byte)0xbf, (byte)0x85, (byte)0x40}, value(0x30, fields));
    }
    private static byte[] record(byte[] software, byte[] tee) {
        return value(4, sequence(value(2, (byte)0x01, (byte)0x90), value(10, (byte)0),
            value(2, (byte)0x01, (byte)0x90), value(10, (byte)1),
            value(4, new byte[32]), value(4, new byte[0]), software, tee));
    }
    private static void rejects(byte[] bytes) {
        try { AttestationRecord.parse(bytes); throw new AssertionError("Accepted malformed DER"); }
        catch (IllegalArgumentException expected) { assertions++; }
    }
    public static void main(String[] args) {
        byte[] input = record(sequence(), sequence(root(true)));
        AttestationRecord modern = AttestationRecord.parse(input);
        check(modern.attestationSecurity == 0 && modern.keyMintSecurity == 1);
        check(modern.challenge.length == 32 && modern.root.state == 2 && !modern.root.locked);
        check(AttestationRecord.allZero(modern.root.key) && AttestationRecord.allZero(modern.root.hash));
        check(AttestationRecord.parse(record(sequence(root(false)), sequence())).root.hash == null);
        check(AttestationRecord.parse(record(sequence(), sequence())).root == null);
        check(!AttestationRecord.allZero(new byte[0]) && !AttestationRecord.allZero(null));
        rejects(record(sequence(root(true)), sequence(root(true))));
        for (int length = 0; length < input.length; length++) rejects(Arrays.copyOf(input, length));
        rejects(join(input, new byte[]{0}));
        rejects(new byte[]{4, (byte)0x80, 0, 0}); // Indefinite length.
        rejects(new byte[]{4, (byte)0x81, 1, 0}); // Nonminimal length.
        rejects(new byte[65537]);
        rejects(null);
        Random random = new Random(11129);
        for (int i = 0; i < 5000; i++) {
            byte[] fuzz = new byte[random.nextInt(1024)]; random.nextBytes(fuzz);
            try { AttestationRecord.parse(fuzz); }
            catch (IllegalArgumentException expected) { assertions++; }
        }
        // High-tag authorization and long-form DER lengths must both parse.
        byte[] unknown = tlv(new byte[]{(byte)0xbf, (byte)0x83, 0x61}, value(4, new byte[256]));
        check(AttestationRecord.parse(record(sequence(unknown), sequence(root(true)))).root.state == 2);
        byte[] applicationId = tlv(new byte[]{(byte)0xbf, (byte)0x85, (byte)0x45}, value(4, new byte[256]));
        check(AttestationRecord.parse(record(sequence(applicationId), sequence(root(true)))).root.state == 2);
        System.out.println("PASS bounded attestation DER: " + assertions + " assertions");
    }
}
