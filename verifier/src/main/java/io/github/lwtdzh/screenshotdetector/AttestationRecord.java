package io.github.lwtdzh.screenshotdetector;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/** Bounded DER reader for the Android key attestation extension. No Android dependencies. */
public final class AttestationRecord {
    public final int attestationSecurity, keyMintSecurity;
    public final byte[] challenge;
    public final RootOfTrust root;
    public static final class RootOfTrust {
        public final byte[] key, hash;
        public final boolean locked;
        public final int state;
        RootOfTrust(List<Node> fields) {
            if (fields.size() != 3 && fields.size() != 4) throw invalid();
            key = fields.get(0).bytes(4);
            Node lock = fields.get(1);
            if (lock.kind != 0 || lock.tag != 1 || lock.length() != 1 ||
                (lock.data[lock.start] != 0 && lock.data[lock.start] != (byte) 0xff)) throw invalid();
            locked = lock.data[lock.start] != 0;
            state = fields.get(2).number(10);
            if (state > 3) throw invalid();
            hash = fields.size() == 4 ? fields.get(3).bytes(4) : null;
        }
    }
    private AttestationRecord(List<Node> fields) {
        if (fields.size() != 8) throw invalid();
        fields.get(0).number(2); // Attestation version.
        attestationSecurity = fields.get(1).number(10);
        fields.get(2).number(2); // Keymaster / KeyMint version.
        keyMintSecurity = fields.get(3).number(10);
        if (attestationSecurity > 2 || keyMintSecurity > 2) throw invalid();
        challenge = fields.get(4).bytes(4);
        fields.get(5).bytes(4); // Unique ID is intentionally not retained.
        RootOfTrust found = null;
        for (int index : new int[]{6, 7}) {
            for (Node auth : fields.get(index).children()) {
                // Android attestation schema: RootOfTrust=[704]; applicationId=[709] is an OCTET STRING.
                if (auth.tag == 704 && auth.kind == 0xa0) {
                    if (found != null) throw invalid();
                    Node sequence = auth.only();
                    found = new RootOfTrust(sequence.children());
                }
            }
        }
        root = found;
    }
    public static AttestationRecord parse(byte[] extensionValue) {
        if (extensionValue == null || extensionValue.length > 65536) throw invalid();
        Node wrapper = Node.one(extensionValue, 0, extensionValue.length, 0);
        byte[] record = wrapper.bytes(4); // X509Certificate.getExtensionValue wraps DER in OCTET STRING.
        return new AttestationRecord(Node.one(record, 0, record.length, 0).children());
    }
    public static boolean allZero(byte[] value) {
        if (value == null || value.length == 0) return false;
        for (byte b : value) if (b != 0) return false;
        return true;
    }
    public static String security(int value) {
        return value == 0 ? "Software" : value == 1 ? "TrustedEnvironment (TEE)" : "StrongBox";
    }
    public static String bootState(int value) {
        return new String[]{"Verified", "SelfSigned", "Unverified", "Failed"}[value];
    }
    private static IllegalArgumentException invalid() {
        return new IllegalArgumentException("Invalid Android attestation DER");
    }
    private static final class Node {
        final byte[] data;
        final int tag, kind, start, end, next, depth;
        Node(byte[] data, int offset, int limit, int depth) {
            if (depth > 12 || offset >= limit) throw invalid();
            this.data = data; this.depth = depth;
            int type = data[offset++] & 255;
            kind = type & 0xe0;
            int parsedTag = type & 31;
            if (parsedTag == 31) {
                parsedTag = 0;
                int count = 0, part;
                do {
                    if (offset >= limit || ++count > 4) throw invalid();
                    part = data[offset++] & 255;
                    if (count == 1 && (part & 127) == 0) throw invalid();
                    parsedTag = (parsedTag << 7) | (part & 127);
                } while ((part & 128) != 0);
                if (parsedTag < 31) throw invalid();
            }
            tag = parsedTag;
            if (offset >= limit) throw invalid();
            int length = data[offset++] & 255;
            if ((length & 128) != 0) {
                int count = length & 127;
                if (count == 0 || count > 3 || offset + count > limit || data[offset] == 0) throw invalid();
                length = 0;
                while (count-- > 0) length = (length << 8) | (data[offset++] & 255);
                if (length < 128) throw invalid();
            }
            if (length > limit - offset) throw invalid();
            start = offset; end = next = start + length;
        }
        static Node one(byte[] data, int start, int limit, int depth) {
            Node node = new Node(data, start, limit, depth);
            if (node.next != limit) throw invalid();
            return node;
        }
        int length() { return end - start; }
        byte[] bytes(int expectedTag) {
            if (kind != 0 || tag != expectedTag) throw invalid();
            return Arrays.copyOfRange(data, start, end);
        }
        int number(int expectedTag) {
            byte[] value = bytes(expectedTag);
            if (value.length == 0 || value.length > 4 || value[0] < 0 ||
                (value.length > 1 && value[0] == 0 && value[1] >= 0)) throw invalid();
            long number = 0;
            for (byte b : value) number = (number << 8) | (b & 255);
            if (number > Integer.MAX_VALUE) throw invalid();
            return (int) number;
        }
        List<Node> children() {
            if (kind != 0x20 || tag != 16) throw invalid();
            List<Node> list = new ArrayList<>();
            for (int offset = start; offset < end;) {
                if (list.size() >= 256) throw invalid();
                Node node = new Node(data, offset, end, depth + 1);
                list.add(node); offset = node.next;
            }
            return list;
        }
        Node only() { return one(data, start, end, depth + 1); }
    }
}
