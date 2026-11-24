#include "vector-hooks.h"
#include "loaded-symbol.h"
#include "property-read.h"
#include <sys/uio.h>
#include <sys/system_properties.h>
#include <cerrno>
#include <string>
#include <fcntl.h>
#include "device-raw-io.h"

namespace {
NativeAPIEntries entries{};
ssize_t (*real_read)(int, void *, size_t) = nullptr;
ssize_t (*real_read_chk)(int, void *, size_t, size_t) = nullptr;
ssize_t (*real_pread)(int, void *, size_t, off_t) = nullptr;
ssize_t (*real_pread64)(int, void *, size_t, off64_t) = nullptr;
ssize_t (*real_readv)(int, const iovec *, int) = nullptr;
size_t (*real_fread)(void *, size_t, size_t, FILE *) = nullptr;
char *(*real_fgets)(char *, int, FILE *) = nullptr;
int (*real_getenforce)() = nullptr;
int (*real_enabled)() = nullptr;
int (*real_property_get)(const char *, char *) = nullptr;
int (*real_property_read)(const prop_info *, char *, char *) = nullptr;
using PropertyCallback = void (*)(void *, const char *, const char *, uint32_t);
void (*real_property_callback)(const prop_info *, PropertyCallback, void *) = nullptr;
using DevicePropertyFilter = const char *(*)(const char *, const char *);
std::atomic<DevicePropertyFilter> devicePropertyFilter{nullptr};
std::atomic<const shield_properties::HandleAdapter *> deviceHandles{nullptr};

bool enforceFd(int fd) {
    int saved = errno;
    char path[64], target[PATH_MAX];
    snprintf(path, sizeof(path), "/proc/self/fd/%d", fd);
    ssize_t n = device_io::link(path, target, sizeof(target) - 1);
    if (n >= 0) target[n] = 0;
    bool match = n >= 0 && (!strcmp(target, "/sys/fs/selinux/enforce")
        || !strcmp(target, "/selinux/enforce"));
    errno = saved;
    return match;
}
void sanitize(void *buffer, size_t length) {
    auto *bytes = static_cast<char *>(buffer);
    for (size_t i = 0; i < length; ++i) if (bytes[i] == '0') bytes[i] = '1';
}
ssize_t filter(int fd, void *buffer, ssize_t n) {
    // Read the real descriptor first: offsets, EOF, failures, dup and close remain kernel-owned.
    if (n > 0 && enforceFd(fd)) sanitize(buffer, static_cast<size_t>(n));
    return n;
}
ssize_t h_read(int fd, void *buffer, size_t count) { return filter(fd, buffer, real_read(fd, buffer, count)); }
ssize_t h_read_chk(int fd, void *buffer, size_t count, size_t capacity) {
    return filter(fd, buffer, real_read_chk(fd, buffer, count, capacity));
}
ssize_t h_pread(int fd, void *buffer, size_t count, off_t offset) {
    return filter(fd, buffer, real_pread(fd, buffer, count, offset));
}
ssize_t h_pread64(int fd, void *buffer, size_t count, off64_t offset) {
    return filter(fd, buffer, real_pread64(fd, buffer, count, offset));
}
ssize_t h_readv(int fd, const iovec *iov, int count) {
    ssize_t n = real_readv(fd, iov, count);
    if (n <= 0 || !enforceFd(fd)) return n;
    size_t remaining = static_cast<size_t>(n);
    for (int i = 0; i < count && remaining; ++i) {
        size_t part = std::min(remaining, iov[i].iov_len);
        sanitize(iov[i].iov_base, part);
        remaining -= part;
    }
    return n;
}
size_t h_fread(void *buffer, size_t size, size_t count, FILE *stream) {
    if (!size || count > SIZE_MAX / size || !enforceFd(fileno(stream)))
        return real_fread(buffer, size, count, stream);
    // fread may consume an incomplete last item while returning zero items.
    size_t bytes = real_fread(buffer, 1, size * count, stream);
    sanitize(buffer, bytes);
    return bytes / size;
}
char *h_fgets(char *buffer, int count, FILE *stream) {
    char *result = real_fgets(buffer, count, stream);
    if (result && enforceFd(fileno(stream))) sanitize(buffer, strlen(buffer));
    return result;
}
int h_getenforce() { return 1; }
int h_enabled() { return 1; }
bool bootProperty(const char *name, const char *value) {
    return name && !strcmp(name, "ro.boot.selinux") && value && *value;
}
const char *propertyFilter(const char *name, const char *value) {
    return bootProperty(name, value) ? "enforcing" : value;
}
int h_property_get(const char *name, char *value) {
    int n = real_property_get(name, value);
    if (bootProperty(name, value)) { strcpy(value, "enforcing"); n = 9; }
    if (auto extra = devicePropertyFilter.load()) {
        std::string replacement = extra(name, value);
        if (replacement != value) {
            return shield_properties::writeLegacy(name, replacement, value);
        }
    }
    return n;
}
int h_property_read(const prop_info *info, char *name, char *value) {
    if(auto adapter=deviceHandles.load()) {
        info=adapter->map(info);
        if(adapter->owns(info)) {
            int result=real_property_read(info,name,value);
            auto source=shield_properties::snapshot(info,real_property_callback);
            return source.captured ? shield_properties::writeLegacy(source.name.c_str(),source.value,value) : result;
        }
    }
    int n = real_property_read(info, name, value);
    auto source = shield_properties::snapshot(info, real_property_callback);
    if (!source.captured) return n;
    const char *key = source.name.c_str();
    std::string replacement = propertyFilter(key, source.value.c_str());
    if (auto extra = devicePropertyFilter.load()) {
        replacement = extra(key, replacement.c_str());
    }
    return replacement == source.value ? n :
        shield_properties::writeLegacy(key, replacement, value);
}
struct PropertyContext { PropertyCallback callback; void *cookie; };
void propertyCallback(void *cookie, const char *name, const char *value, uint32_t serial) {
    auto *context = static_cast<PropertyContext *>(cookie);
    std::string replacement = bootProperty(name, value) ? "enforcing" : value;
    if (auto extra = devicePropertyFilter.load()) replacement = extra(name, replacement.c_str());
    context->callback(context->cookie, name, replacement.c_str(), serial);
}
void h_property_callback(const prop_info *info, PropertyCallback callback, void *cookie) {
    if(auto adapter=deviceHandles.load()) {
        info=adapter->map(info);
        if(adapter->owns(info)) { real_property_callback(info,callback,cookie);return; }
    }
    PropertyContext context{callback, cookie};
    real_property_callback(info, propertyCallback, &context);
}

bool externalRedirect(void *symbol) {
#if defined(__aarch64__)
    uint32_t words[2];
    memcpy(words, symbol, sizeof(words));
    uintptr_t target = 0;
    if ((words[0] & 0xfc000000u) == 0x14000000u) {
        int64_t offset = words[0] & 0x03ffffffu;
        if (offset & 0x02000000) offset -= 0x04000000;
        target = reinterpret_cast<uintptr_t>(symbol) + offset * 4;
    } else if ((words[0] & 0xffffffe0u) == 0x58000040u
        && (words[1] & 0xfffffc1fu) == 0xd61f0000u
        && (words[0] & 31u) == ((words[1] >> 5) & 31u)) {
        memcpy(&target, static_cast<const char *>(symbol) + 8, sizeof(target));
    }
    if (!target) return false;
    Dl_info source{}, destination{};
    if (!dladdr(symbol, &source)) return false;
    if (!dladdr(reinterpret_cast<void *>(target), &destination)) return true;
    if (destination.dli_fbase == source.dli_fbase) return false;
    // These libraries belong to this module and deliberately chain the same libc APIs.
    const char *path = destination.dli_fname ? destination.dli_fname : "";
    const char *name = strrchr(path, '/');
    name = name ? name + 1 : path;
    return strcmp(name, "libshield.so") && strcmp(name, "libdeveloperstate.so");
#else
    (void) symbol;
    return false;
#endif
}
template <class R, class O>
void addSymbol(void *symbol, const char *name, R replacement, O *original) {
    if (!symbol || hookedSymbols.count(symbol)) return;
    if (symbolSize(symbol, name) < 16 || externalRedirect(symbol)) {
        __android_log_print(ANDROID_LOG_WARN, "SELinuxStateShield", "native entry retained: %s", name);
        return;
    }
    uint8_t before[64];
    size_t captured = std::min(symbolSize(symbol, name), sizeof(before));
    memcpy(before, symbol, captured);
    int hookResult = -1;
#if defined(__aarch64__)
    hookResult = shield_entry::install(symbol, reinterpret_cast<void *>(replacement),
        reinterpret_cast<void **>(original));
#endif
    if (hookResult == 0 || entries.hookFunc(symbol, reinterpret_cast<void *>(replacement),
        reinterpret_cast<void **>(original)) == 0) {
        hookedSymbols.insert(symbol);
        codeViews.remember(reinterpret_cast<uintptr_t>(symbol), before, symbol, captured);
        ++hookCount;
    } else __android_log_print(ANDROID_LOG_WARN, "SELinuxStateShield", "native hook failed: %s", name);
}
template <class R, class O>
void add(void *handle, const char *name, R replacement, O *original) {
    addSymbol(dlsym(handle, name), name, replacement, original);
}
template <class R, class O>
bool addRead(const char *name, R replacement, O *original) {
    void *symbol = dlsym(RTLD_DEFAULT, name);
    using Register = bool (*)(void *, ssize_t (*)(int, void *, ssize_t));
    auto registrar = reinterpret_cast<Register>(
        loadedSymbol("libshield.so", "appstateshield_set_selinux_read_filter"));
    // Vector rejects a second Hook on one address. Compose with our already
    // installed read wrappers, and only fall back when that entry is not owned.
    if (registrar && registrar(symbol, filter)) return true;
    addSymbol(symbol, name, replacement, original);
    return hookedSymbols.count(symbol) != 0;
}
template <class R, class O>
void addProperty(const char *name, R replacement, O *original) {
    void *symbol = dlsym(RTLD_DEFAULT, name);
    using Register = bool (*)(void *, const char *(*)(const char *, const char *));
    auto registrar = reinterpret_cast<Register>(
        loadedSymbol("libdeveloperstate.so", "appstateshield_set_selinux_property_filter"));
    if (registrar && registrar(symbol, propertyFilter)) return;
    addSymbol(symbol, name, replacement, original);
}
void selinuxLibrary(void *handle) {
    add(handle, "security_getenforce", h_getenforce, &real_getenforce);
    add(handle, "is_selinux_enabled", h_enabled, &real_enabled);
    addSymbol(loadedSymbol("libselinux.so", "security_getenforce"), "security_getenforce", h_getenforce, &real_getenforce);
    addSymbol(loadedSymbol("libselinux.so", "is_selinux_enabled"), "is_selinux_enabled", h_enabled, &real_enabled);
}
void onLoaded(const char *path, void *handle) {
    const char *name = path ? strrchr(path, '/') : nullptr;
    name = name ? name + 1 : path;
    if (name && !strcmp(name, "libselinux.so")) selinuxLibrary(handle);
}
}
extern "C" __attribute__((visibility("default"))) void
appstateshield_set_device_property_handles(const shield_properties::HandleAdapter *adapter) {
    deviceHandles.store(adapter);
}
extern "C" __attribute__((visibility("default"))) bool
appstateshield_set_device_property_filter(void *symbol, const char *(*filter)(const char *, const char *)) {
    if (!hookedSymbols.count(symbol) || !real_property_get || !real_property_read || !real_property_callback) return false;
    devicePropertyFilter.store(filter);
    return true;
}
extern "C" __attribute__((visibility("default"))) OnLoad native_init(const NativeAPIEntries *api) {
    if (!api || api->version < 1 || !api->hookFunc) return nullptr;
    entries = *api;
    anonymizeLinkerFileViews();
    real_property_callback=reinterpret_cast<shield_properties::ReadCallback>(
        dlsym(RTLD_DEFAULT,"__system_property_read_callback"));
    // Vector holds its loader locks: RTLD_DEFAULT and the supplied on-load handle only.
#define ADD(name, replacement, original) add(RTLD_DEFAULT, name, replacement, &original)
    bool bufferedReadCovered = addRead("read", h_read, &real_read);
    addRead("__read_chk", h_read_chk, &real_read_chk);
    addRead("pread", h_pread, &real_pread);
    addRead("pread64", h_pread64, &real_pread64);
    addRead("readv", h_readv, &real_readv);
    // Bionic's FILE refill calls read, which already filters every byte before
    // buffering (including an incomplete fread item). Rechecking the descriptor
    // for each buffered fread/fgets adds a readlink syscall to otherwise local
    // reads; SecurityGuard performs these while holding its startup lock.
    if (!bufferedReadCovered) {
        ADD("fread", h_fread, real_fread);
        ADD("fgets", h_fgets, real_fgets);
    }
    addProperty("__system_property_get", h_property_get, &real_property_get);
    addProperty("__system_property_read", h_property_read, &real_property_read);
    addProperty("__system_property_read_callback", h_property_callback, &real_property_callback);
#undef ADD
    selinuxLibrary(RTLD_DEFAULT);
    __android_log_print(ANDROID_LOG_INFO, "SELinuxStateShield", "native ready hooks=%d", hookCount.load());
    return onLoaded;
}
extern "C" __attribute__((visibility("default"))) jint JNI_OnLoad(JavaVM *, void *) {
    return JNI_VERSION_1_6;
}
