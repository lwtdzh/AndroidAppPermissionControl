#include "vector-hooks.h"
#include <sys/system_properties.h>
#include <string>
namespace {
int (*real_get)(const char *, char *) = nullptr;
int (*real_read)(const prop_info *, char *, char *) = nullptr;
using Callback = void (*)(void *, const char *, const char *, uint32_t);
void (*real_callback)(const prop_info *, Callback, void *) = nullptr;
std::string sanitize(const char *key, const char *value) {
    std::string name = key ? key : "", original = value ? value : "";
    if (name == "init.svc.adbd") return "stopped";
    if (name == "init.svc_debug_pid.adbd") return "";
    if (name == "service.adb.tcp.port" || name == "persist.adb.tcp.port") return "-1";
    if (name == "persist.service.adb.enable" || name == "persist.sys.adb_enabled"
        || name == "sys.usb.ffs.ready") return "0";
    if (name == "sys.usb.state" || name == "sys.usb.config" || name == "persist.sys.usb.config") {
        std::string kept;
        size_t start = 0;
        do {
            size_t end = original.find(',', start);
            std::string token = original.substr(start, end == std::string::npos ? end : end - start);
            if (!token.empty() && token != "adb") { if (!kept.empty()) kept += ','; kept += token; }
            if (end == std::string::npos) break;
            start = end + 1;
        } while (start <= original.size());
        return kept.empty() ? "none" : kept;
    }
    return original;
}
int h_get(const char *key, char *value) {
    int result = real_get(key, value);
    std::string replacement = sanitize(key, value);
    if (replacement != value) {
        size_t length = std::min(replacement.size(), static_cast<size_t>(PROP_VALUE_MAX - 1));
        memcpy(value, replacement.c_str(), length + 1);
        return static_cast<int>(length);
    }
    return result;
}
int h_read(const prop_info *info, char *name, char *value) {
    int result = real_read(info, name, value);
    std::string replacement = sanitize(name, value);
    if (replacement != value) {
        size_t length = std::min(replacement.size(), static_cast<size_t>(PROP_VALUE_MAX - 1));
        memcpy(value, replacement.c_str(), length + 1);
        return static_cast<int>(length);
    }
    return result;
}
struct Context { Callback callback; void *cookie; };
void filtered_callback(void *cookie, const char *name, const char *value, uint32_t serial) {
    auto *context = static_cast<Context *>(cookie);
    std::string replacement = sanitize(name, value);
    context->callback(context->cookie, name, replacement.c_str(), serial);
}
void h_callback(const prop_info *info, Callback callback, void *cookie) {
    // Bionic's property callback is synchronous; context lifetime spans the complete call.
    Context context{callback, cookie};
    real_callback(info, filtered_callback, &context);
}
}
extern "C" __attribute__((visibility("default"))) OnLoad native_init(const NativeAPIEntries *api) {
    if (!api || api->version < 1 || !api->hookFunc) return nullptr;
    anonymizeLinkerFileViews();
    install(api, "__system_property_get", h_get, &real_get);
    install(api, "__system_property_read", h_read, &real_read);
    install(api, "__system_property_read_callback", h_callback, &real_callback);
    __android_log_print(ANDROID_LOG_INFO, "DeveloperStateShield", "native ready hooks=%d", hookCount.load());
    return nullptr;
}
extern "C" __attribute__((visibility("default"))) jint JNI_OnLoad(JavaVM *, void *) {
    return JNI_VERSION_1_6;
}
