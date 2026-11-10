#include <jni.h>
#include <sys/system_properties.h>
#include <ifaddrs.h>
#include <unistd.h>
#include <link.h>
#include <string>
#include <set>
namespace {
std::string quoted(const char *value) {
    std::string out = "\"";
    for (const char *p = value; *p; ++p) {
        if (*p == '\\' || *p == '"') out += '\\';
        if (static_cast<unsigned char>(*p) < 32) continue;
        out += *p;
    }
    return out + "\"";
}
void callback(void *cookie, const char *, const char *value, uint32_t) {
    *static_cast<std::string *>(cookie) = value;
}
int libraries(dl_phdr_info *info, size_t, void *cookie) {
    std::string path = info->dlpi_name ? info->dlpi_name : "";
    std::string name = path.substr(path.find_last_of('/') + 1);
    if (name == "libshield.so" || name == "libvpnstate.so" || name == "libdeveloperstate.so")
        static_cast<std::set<std::string> *>(cookie)->insert(name);
    return 0;
}
}
extern "C" JNIEXPORT jstring JNICALL
Java_io_github_lwtdzh_devicestateprobe_ProbeActivity_nativeSnapshot(JNIEnv *env, jobject) {
    std::string out = "{";
    for (const char *key : {"init.svc.adbd", "sys.usb.config", "sys.usb.state",
        "service.adb.tcp.port", "ro.build.version.sdk"}) {
        char value[PROP_VALUE_MAX]{}, name[256]{};
        __system_property_get(key, value);
        out += quoted((std::string(key) + ".get").c_str()) + ":" + quoted(value) + ",";
        const prop_info *info = __system_property_find(key);
        if (info) {
            __system_property_read(info, name, value);
            out += quoted((std::string(key) + ".read").c_str()) + ":" + quoted(value) + ",";
            std::string result;
            __system_property_read_callback(info, callback, &result);
            out += quoted((std::string(key) + ".callback").c_str()) + ":" + quoted(result.c_str()) + ",";
        }
    }
    std::set<std::string> interfaces;
    bool ok = true;
    // Repeat paired allocation/free to catch list ownership bugs, retaining ordinary interfaces.
    for (int i = 0; i < 64; ++i) {
        ifaddrs *list = nullptr;
        if (getifaddrs(&list)) { ok = false; break; }
        for (auto *item = list; item; item = item->ifa_next)
            if (item->ifa_name) interfaces.emplace(item->ifa_name);
        freeifaddrs(list);
    }
    out += "\"interfaces\":[";
    bool first = true;
    for (const auto &name : interfaces) { if (!first) out += ','; first = false; out += quoted(name.c_str()); }
    out += "],\"listLifetimeOk\":" + std::string(ok ? "true" : "false");
    out += ",\"getpidOk\":" + std::string(getpid() > 0 ? "true" : "false");
    std::set<std::string> loaded;
    dl_iterate_phdr(libraries, &loaded);
    out += ",\"protectionLibraries\":[";
    first = true;
    for (const auto &name : loaded) { if (!first) out += ','; first = false; out += quoted(name.c_str()); }
    out += "]}";
    return env->NewStringUTF(out.c_str());
}
