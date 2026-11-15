package io.github.lwtdzh.deviceprofile;

/** Request tags only. Challenge, key authorization and certificate data are untouched. */
public final class AttestationPrivacy {
    private AttestationPrivacy() {}
    public static boolean remove(int tag, DeviceProfile profile) {
        if (!profile.enabled) return false;
        // Keymaster/KeyMint stable typed tag values (BYTES = 9, BOOL = 7).
        switch (tag) {
            case 0x900002c6: return profile.get("brand") != null; // ATTESTATION_ID_BRAND 710
            case 0x900002c7: return profile.get("device") != null;
            case 0x900002c8: return profile.get("product") != null;
            case 0x900002c9: return profile.get("serial") != null;
            case 0x900002ca: return profile.get("imei") != null;
            case 0x900002cb: return profile.get("meid") != null;
            case 0x900002cc: return profile.get("manufacturer") != null;
            case 0x900002cd: return profile.get("model") != null;
            case 0x900002d3: return profile.get("imei2") != null; // SECOND_IMEI 723
            case 0x700002d0: // DEVICE_UNIQUE_ATTESTATION 720
            case 0x700000ca: // INCLUDE_UNIQUE_ID 202
                return profile.get("serial") != null || profile.get("imei") != null ||
                    profile.get("imei2") != null || profile.get("meid") != null;
            default: return false;
        }
    }
}
