#include <jni.h>
#include <dlfcn.h>
#include <link.h>
#include <android/log.h>
#include <cstring>
#include <cstdio>
#include <cinttypes>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/uio.h>
#include <array>
#include <vector>
#include "loaded-symbol.h"
#include "entry-hook.h"
#include "device-raw-io.h"
#include "elf-code-view.h"
#include "process-code-view.h"

extern "C" {
__attribute__((visibility("hidden"))) long (*compat_original_syscall)(long, ...) = nullptr;
__attribute__((visibility("hidden"))) long compat_syscall_dispatch(long, ...);
}

namespace {
using Hook = int (*)(void *, void *, void **);
Hook originalHook = nullptr;
shield_entry::Detour adapter;
thread_local bool preparing = false;
shield_code::Views frameworkViews;
shield_code::Views ownViews;
struct Range { uintptr_t begin, end; };
std::vector<Range> vectorCode;
using Overlay = void (*)(uintptr_t, void *, size_t);
ssize_t (*originalRead)(pid_t, const iovec *, unsigned long, const iovec *, unsigned long, unsigned long) = nullptr;

void overlayCode(uintptr_t at, void *buffer, size_t n) {
    // 后安装的包装器先还原，再还原前一层；保留后来第三方改写的字节。
    for (const char *name : {"libdevicestate.so", "libselinuxstate.so", "libdeveloperstate.so",
                            "libvpnstate.so", "libshield.so"}) {
        auto overlay = reinterpret_cast<Overlay>(loadedSymbol(name, "appstateshield_overlay_own_code"));
        if (overlay) overlay(at, buffer, n);
    }
    ownViews.overlay(at, buffer, n);
    frameworkViews.overlay(at, buffer, n);
}
template<class Read>
ssize_t readProcess(pid_t pid, const iovec *local, unsigned long lc,
                    const iovec *remote, unsigned long rc, unsigned long flags, Read read) {
    if (pid != getpid() || flags || lc > 1024 || rc > 1024 || !lc || !rc) return read();
    // 先用内核复制描述符；错误参数交回原函数，不能在包装器内直接解引用。
    std::vector<iovec> l(lc), r(rc);
    iovec output[] = {{l.data(), lc * sizeof(iovec)}, {r.data(), rc * sizeof(iovec)}};
    iovec input[] = {{const_cast<iovec *>(local), lc * sizeof(iovec)},
                     {const_cast<iovec *>(remote), rc * sizeof(iovec)}};
    int prior = errno;
    ssize_t descriptors = device_io::call(__NR_process_vm_readv, pid,
        reinterpret_cast<long>(output), 2, reinterpret_cast<long>(input), 2);
    errno = prior;
    if (descriptors != static_cast<ssize_t>((lc + rc) * sizeof(iovec))) return read();
    ssize_t result = read();
    int saved = errno;
    shield_code::overlayRead(l.data(), lc, r.data(), rc, result, overlayCode);
    errno = saved;
    return result;
}
ssize_t compatibleRead(pid_t pid, const iovec *local, unsigned long lc,
                       const iovec *remote, unsigned long rc, unsigned long flags) {
    return readProcess(pid, local, lc, remote, rc, flags,
        [&] { return originalRead(pid, local, lc, remote, rc, flags); });
}

void *vectorSymbol(const char *name) {
    struct Query { const char *name; void *result; } query{name, nullptr};
    dl_iterate_phdr([](dl_phdr_info *info, size_t, void *cookie) {
        auto *q = static_cast<Query *>(cookie);
        const char *path = info->dlpi_name;
        if (!path || !*path) return 0;
        const char *base = strrchr(path, '/');
        q->result = loadedSymbol(base ? base + 1 : path, q->name);
        return q->result ? 1 : 0;
    }, &query);
    return query.result;
}
void captureArt(void *vectorEntry) {
    struct Query { uintptr_t entry; } query{reinterpret_cast<uintptr_t>(vectorEntry)};
    dl_iterate_phdr([](dl_phdr_info *info, size_t, void *cookie) {
        auto entry = static_cast<Query *>(cookie)->entry;
        bool owner = false;
        for (size_t i = 0; i < info->dlpi_phnum; ++i) {
            const auto &p = info->dlpi_phdr[i];
            uintptr_t start = info->dlpi_addr + p.p_vaddr;
            if (p.p_type == PT_LOAD && entry >= start && entry - start < p.p_memsz) owner = true;
        }
        if (owner) for (size_t i = 0; i < info->dlpi_phnum; ++i) {
            const auto &p = info->dlpi_phdr[i];
            uintptr_t start = info->dlpi_addr + p.p_vaddr;
            if (p.p_type == PT_LOAD && (p.p_flags & PF_X) && p.p_memsz <= UINTPTR_MAX - start)
                vectorCode.push_back({start, start + p.p_memsz});
        }
        return 0;
    }, &query);
    dl_iterate_phdr([](dl_phdr_info *info, size_t, void *) {
        const char *name = info->dlpi_name ? strrchr(info->dlpi_name, '/') : nullptr;
        if (!name || strcmp(name + 1, "libart.so")) return 0;
        int fd = device_io::open(info->dlpi_name, O_RDONLY | O_CLOEXEC);
        if (fd < 0) return 0;
        struct stat metadata{};
        size_t count = 0;
        if (!device_io::stat(fd, &metadata) && metadata.st_size > 0 && metadata.st_size <= 128 * 1024 * 1024) {
            size_t size = static_cast<size_t>(metadata.st_size);
            void *file = device_io::map(nullptr, size, PROT_READ, MAP_PRIVATE, fd, 0);
            if (file != MAP_FAILED) {
                count = shield_code::captureElf(file, size, info->dlpi_addr, info->dlpi_phdr,
                    info->dlpi_phnum, [](uintptr_t target) {
                        for (const auto &range : vectorCode)
                            if (target >= range.begin && target < range.end) return true;
                        return false;
                    }, frameworkViews);
                device_io::call(__NR_munmap, reinterpret_cast<long>(file), size);
            }
        }
        device_io::close(fd);
        __android_log_print(ANDROID_LOG_INFO, "AppStateShield", "ART code views=%zu", count);
        return 0;
    }, nullptr);
}
int installOwned(void *symbol, void *replacement, void **original) {
    if (!symbol) return -1;
    uint8_t before[16];
    memcpy(before, symbol, sizeof(before));
    int result = shield_entry::install(symbol, replacement, original);
    if (result && originalHook) result = originalHook(symbol, replacement, original);
    if (!result) ownViews.remember(reinterpret_cast<uintptr_t>(symbol), before, symbol, sizeof(before));
    return result;
}
int compatibleHook(void *symbol, void *replacement, void **original) {
    if (preparing) {
        return installOwned(symbol, replacement, original);
    }
    return originalHook(symbol, replacement, original);
}
}
extern "C" JNIEXPORT jboolean JNICALL
Java_io_github_lwtdzh_appstateshield_NativeLibraries_prepare(JNIEnv *, jclass) {
#if defined(__aarch64__)
    void *entry = vectorSymbol("DobbyHook");
    if (!entry) return false;
    captureArt(entry);
    int result = shield_entry::install(entry, reinterpret_cast<void *>(compatibleHook),
        reinterpret_cast<void **>(&originalHook), &adapter);
    preparing = result == 0;
    if (preparing) {
        installOwned(dlsym(RTLD_DEFAULT, "syscall"), reinterpret_cast<void *>(compat_syscall_dispatch),
                     reinterpret_cast<void **>(&compat_original_syscall));
        installOwned(dlsym(RTLD_DEFAULT, "process_vm_readv"), reinterpret_cast<void *>(compatibleRead),
                     reinterpret_cast<void **>(&originalRead));
    }
    __android_log_print(ANDROID_LOG_INFO, "AppStateShield", "native compatibility ready=%d", preparing);
    return preparing;
#else
    return false;
#endif
}
extern "C" JNIEXPORT void JNICALL
Java_io_github_lwtdzh_appstateshield_NativeLibraries_finish(JNIEnv *, jclass) {
    if (!preparing) return;
    preparing = false;
    __android_log_print(ANDROID_LOG_INFO, "AppStateShield", "native adapter restored=%d",
        shield_entry::restore(adapter));
}
extern "C" __attribute__((visibility("hidden"))) long compat_filtered_syscall(
    long number, long a1, long a2, long a3, long a4, long a5, long a6) {
    return readProcess(static_cast<pid_t>(a1), reinterpret_cast<const iovec *>(a2), a3,
        reinterpret_cast<const iovec *>(a4), a5, a6,
        [&] { return compat_original_syscall(number, a1, a2, a3, a4, a5, a6); });
}
extern "C" __attribute__((visibility("default"))) void
appstateshield_overlay_own_code(uintptr_t at, void *buffer, size_t n) {
    ownViews.overlay(at, buffer, n);
    frameworkViews.overlay(at, buffer, n);
}
extern "C" __attribute__((visibility("default"))) bool
appstateshield_owns_entry(const void *address) { return ownViews.owns(address); }
extern "C" JNIEXPORT jint JNI_OnLoad(JavaVM *, void *) { return JNI_VERSION_1_6; }
