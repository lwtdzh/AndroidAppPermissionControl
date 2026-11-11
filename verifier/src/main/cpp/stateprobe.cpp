#include <jni.h>
#include <sys/system_properties.h>
#include <ifaddrs.h>
#include <unistd.h>
#include <link.h>
#include <string>
#include <set>
#include <dlfcn.h>
#include <fcntl.h>
#include <sys/uio.h>
#include <sys/syscall.h>
#include <cerrno>
#include <cstdio>
#include "loaded-symbol.h"
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
    if (name == "libshield.so" || name == "libvpnstate.so" || name == "libdeveloperstate.so"
        || name == "libselinuxstate.so")
        static_cast<std::set<std::string> *>(cookie)->insert(name);
    return 0;
}
extern "C" JNIEXPORT jstring JNICALL
Java_io_github_lwtdzh_devicestateprobe_SelinuxProbe_nativeSnapshot(JNIEnv *env, jclass, jstring ordinary) {
    std::string out = "{";
    auto put = [&](const char *key, const std::string &value) { out += quoted(key) + ":" + quoted(value.c_str()) + ","; };
    auto bytes = [](ssize_t n, const char *buffer) {
        return n < 0 ? std::string("ERROR:") + std::to_string(errno) : std::string(buffer, static_cast<size_t>(n));
    };
    const char *path = "/sys/fs/selinux/enforce";
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    char buffer[16]{};
    put("read", bytes(read(fd, buffer, 1), buffer));
    put("eof", std::to_string(read(fd, buffer, 1)));
    put("pread", bytes(pread(fd, buffer, 1, 0), buffer));
    put("pread64", bytes(pread64(fd, buffer, 1, 0), buffer));
    lseek(fd, 0, SEEK_SET);
    iovec iov[]{{buffer, 0}, {buffer, 1}};
    put("readv", bytes(readv(fd, iov, 2), buffer));
    int alias = dup(fd);
    lseek(alias, 0, SEEK_SET);
    put("dup", bytes(read(alias, buffer, 1), buffer));
    close(alias);
    // A direct syscall intentionally bypasses libc read. Record this limitation.
    put("directSyscall", bytes(syscall(__NR_pread64, fd, buffer, 1, 0), buffer));
    close(fd);
    errno = 0;
    ssize_t invalid = read(-1, buffer, 1);
    put("badFd", invalid == -1 && errno == EBADF ? "EBADF" : "BROKEN");
    FILE *stream = fopen(path, "r");
    if (stream) {
        size_t n = fread(buffer, 1, 1, stream);
        put("fread", std::string(buffer, n));
        rewind(stream);
        memset(buffer, '?', sizeof(buffer));
        n = fread(buffer, 2, 1, stream);
        put("freadPartial", std::string(buffer, 1));
        put("freadPartialItems", std::to_string(n));
        rewind(stream);
        put("fgets", fgets(buffer, sizeof(buffer), stream) ? buffer : "ERROR");
        fclose(stream);
    } else put("fread", "ERROR");
    if (loadedSymbol("libselinux.so", "security_getenforce")) {
        for (const char *name : {"security_getenforce", "is_selinux_enabled"}) {
            auto function = reinterpret_cast<int (*)()>(loadedSymbol("libselinux.so", name));
            put(name, function ? std::to_string(function()) : "UNAVAILABLE");
        }
        auto getcon = reinterpret_cast<int (*)(char **)>(loadedSymbol("libselinux.so", "getcon"));
        auto freecon = reinterpret_cast<void (*)(char *)>(loadedSymbol("libselinux.so", "freecon"));
        char *context = nullptr;
        bool ok = getcon && freecon && getcon(&context) == 0 && context && *context;
        put("contextAvailable", ok ? "true" : "false");
        if (context && freecon) freecon(context);
    } else put("security_getenforce", "UNAVAILABLE");
    const char *normal = env->GetStringUTFChars(ordinary, nullptr);
    fd = open(normal, O_RDONLY | O_CLOEXEC);
    put("ordinaryRead", bytes(read(fd, buffer, 1), buffer));
    close(fd);
    env->ReleaseStringUTFChars(ordinary, normal);
    out += "\"done\":true}";
    return env->NewStringUTF(out.c_str());
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
