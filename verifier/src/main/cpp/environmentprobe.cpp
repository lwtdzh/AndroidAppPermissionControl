#include <jni.h>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <link.h>
#include <string>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/system_properties.h>
#include <unistd.h>

static std::string quote(const std::string& value) {
    std::string out = "\"";
    for (unsigned char c : value) {
        if (c == '"' || c == '\\') { out += '\\'; out += c; }
        else if (c >= 32 && c < 127) out += c;
        else { char escaped[7]; snprintf(escaped, sizeof(escaped), "\\u%04x", c); out += escaped; }
    }
    return out + "\"";
}
static bool suspicious(const std::string& path) {
    return path.find("/data/adb/") != std::string::npos ||
        path.find("libzygisk") != std::string::npos ||
        path.find("zygisk_vector") != std::string::npos ||
        path.find("libxposed") != std::string::npos ||
        path.find("liblsplant") != std::string::npos ||
        path.find("liblspd") != std::string::npos ||
        path.find("libsubstrate") != std::string::npos;
}
static int library(struct dl_phdr_info* info, size_t, void* destination) {
    auto* paths = static_cast<std::string*>(destination);
    std::string path = info->dlpi_name ? info->dlpi_name : "";
    if (suspicious(path) && paths->size() < 65536) {
        if (!paths->empty()) *paths += ",";
        *paths += quote(path);
    }
    return 0;
}
static std::string accessResult(int result, int error) {
    if (result == 0) return "\"present\"";
    if (error == ENOENT || error == ENOTDIR) return "\"absent\"";
    return quote("unknown:errno=" + std::to_string(error));
}
extern "C" JNIEXPORT jstring JNICALL
Java_io_github_lwtdzh_screenshotdetector_EnvironmentProbe_nativeRead(JNIEnv* env, jclass) {
    std::string result = "{\"files\":[";
    const char* files[] = {"/system/bin/su", "/system/xbin/su", "/sbin/su", "/su/bin/su",
        "/system/bin/busybox", "/system/xbin/busybox", "/data/adb/magisk",
        "/data/adb/ksu", "/data/adb/modules", "/sbin/.magisk"};
    bool first = true;
    for (const char* file : files) {
        if (!first) result += ",";
        first = false;
        struct stat st{};
        errno = 0;
        int exists = stat(file, &st), error = errno;
        errno = 0;
        long raw = syscall(SYS_faccessat, AT_FDCWD, file, F_OK), rawError = errno;
        result += "{\"path\":" + quote(file) + ",\"libc\":" + accessResult(exists, error) +
            ",\"syscall\":" + accessResult(static_cast<int>(raw), static_cast<int>(rawError)) + "}";
    }
    result += "],\"maps\":";
    std::string maps;
    FILE* input = fopen("/proc/self/maps", "re");
    bool truncated = false;
    int mapsError = input ? 0 : errno;
    if (input) {
        char line[4096]; size_t total = 0;
        while (fgets(line, sizeof(line), input)) {
            total += strlen(line);
            if (total > 2 * 1024 * 1024) { truncated = true; break; }
            char* path = strchr(line, '/');
            if (path && suspicious(path) && maps.size() < 65536) {
                path[strcspn(path, "\r\n")] = 0;
                if (!maps.empty()) maps += ",";
                maps += quote(path);
            }
        }
        if (ferror(input)) mapsError = errno ? errno : EIO;
        fclose(input);
    }
    result += "[" + maps + "],\"mapsError\":" + std::to_string(mapsError) +
        ",\"mapsTruncated\":" + (truncated ? "true" : "false") + ",\"linker\":[";
    std::string loaded;
    dl_iterate_phdr(library, &loaded);
    result += loaded + "],\"properties\":{";
    const char* properties[] = {"ro.build.tags", "ro.build.type", "ro.debuggable", "ro.secure",
        "ro.vendor_dlkm.build.tags", "ro.odm_dlkm.build.tags", "ro.system_dlkm.build.tags",
        "ro.boot.verifiedbootstate", "ro.boot.flash.locked", "ro.boot.vbmeta.device_state",
        "ro.boot.veritymode", "ro.boot.selinux"};
    first = true;
    for (const char* key : properties) {
        char value[PROP_VALUE_MAX]{};
        __system_property_get(key, value);
        if (!first) result += ",";
        first = false;
        result += quote(key) + ":" + quote(value);
    }
    result += "},\"selinux\":";
    char value = 0;
    int fd = open("/sys/fs/selinux/enforce", O_RDONLY | O_CLOEXEC);
    int enforceError = fd < 0 ? errno : 0;
    if (fd >= 0) {
        ssize_t count = read(fd, &value, 1);
        if (count != 1) enforceError = count < 0 ? errno : EIO;
        close(fd);
    }
    result += quote(enforceError ? "unknown:errno=" + std::to_string(enforceError) :
        value == '1' ? "Enforcing" : value == '0' ? "Permissive" : "unknown:invalid byte");
    result += "}";
    return env->NewStringUTF(result.c_str());
}
