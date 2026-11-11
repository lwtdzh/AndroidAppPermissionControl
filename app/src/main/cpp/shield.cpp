#include <android/log.h>
#include <jni.h>
#include <link.h>
#include <dlfcn.h>
#include <dirent.h>
#include <fcntl.h>
#include <sys/inotify.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/uio.h>
#include <sys/mman.h>
#include <cstdlib>
#include <unistd.h>
#include <cerrno>
#include <climits>
#include <cstddef>
#include <cstdarg>
#include <cstdio>
#include <cstdint>
#include <cinttypes>
#include <cstring>
#include <algorithm>
#include <atomic>
#include <mutex>
#include <memory>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

// Public Vector ABI, checked against Vector v2.2/native/include/core/native_api.h.
using Hook = int (*)(void *, void *, void **);
using OnLoad = void (*)(const char *, void *);
struct NativeAPIEntries { uint32_t version; Hook hookFunc; int (*unhookFunc)(void *); };

extern "C" {
__attribute__((visibility("hidden"))) long (*shield_original_syscall)(long, ...) = nullptr;
__attribute__((visibility("hidden"))) long shield_syscall_dispatch(long, ...);
}

namespace {
std::atomic<int> hookCount{0};
std::atomic<int> blockCount{0};
thread_local bool internal = false;
struct InternalGuard {
    bool previous = internal;
    InternalGuard() { internal = true; }
    ~InternalGuard() { internal = previous; }
};
std::mutex watchesMutex;
struct Watch { std::string path; uint32_t mask; };
using WatchMap = std::unordered_map<int, Watch>;
// dup aliases share one kernel watch set; additions/IN_IGNORED must be visible through all aliases.
std::unordered_map<int, std::shared_ptr<WatchMap>> watches;
std::unordered_set<void *> hookedSymbols;
std::unordered_set<void *> successfulHooks;
using ReadFilter = ssize_t (*)(int, void *, ssize_t);
std::atomic<ReadFilter> extraReadFilter{nullptr};
ssize_t afterRead(int fd, void *buffer, ssize_t n) {
    auto filter = extraReadFilter.load();
    return filter ? filter(fd, buffer, n) : n;
}
ssize_t afterReadv(int fd, const iovec *iov, int count, ssize_t n) {
    size_t remaining = n > 0 ? static_cast<size_t>(n) : 0;
    for (int i = 0; i < count && remaining; ++i) {
        size_t part = std::min(remaining, iov[i].iov_len);
        afterRead(fd, iov[i].iov_base, static_cast<ssize_t>(part));
        remaining -= part;
    }
    return n;
}

int (*real_open)(const char *, int, ...) = nullptr;
int (*real_openat)(int, const char *, int, ...) = nullptr;
int (*real_open_2)(const char *, int) = nullptr;
int (*real_openat_2)(int, const char *, int) = nullptr;
int (*real_access)(const char *, int) = nullptr;
int (*real_faccessat)(int, const char *, int, int) = nullptr;
int (*real_stat)(const char *, struct stat *) = nullptr;
int (*real_lstat)(const char *, struct stat *) = nullptr;
int (*real_fstatat)(int, const char *, struct stat *, int) = nullptr;
int (*real_stat64)(const char *, struct stat64 *) = nullptr;
int (*real_lstat64)(const char *, struct stat64 *) = nullptr;
int (*real_fstatat64)(int, const char *, struct stat64 *, int) = nullptr;
int (*real_fstat)(int, struct stat *) = nullptr;
int (*real_fstat64)(int, struct stat64 *) = nullptr;
char *(*real_realpath)(const char *, char *) = nullptr;
ssize_t (*real_pread)(int, void *, size_t, off_t) = nullptr;
ssize_t (*real_pread64)(int, void *, size_t, off64_t) = nullptr;
void *(*real_mmap)(void *, size_t, int, int, int, off_t) = nullptr;
void *(*real_mmap64)(void *, size_t, int, int, int, off64_t) = nullptr;
int (*real_fcntl)(int, int, ...) = nullptr;
ssize_t (*real_preadv)(int, const struct iovec *, int, off_t) = nullptr;
ssize_t (*real_preadv64)(int, const struct iovec *, int, off64_t) = nullptr;
int (*real_statx)(int, const char *, int, unsigned int, struct statx *) = nullptr;
FILE *(*real_fopen)(const char *, const char *) = nullptr;
FILE *(*real_freopen)(const char *, const char *, FILE *) = nullptr;
DIR *(*real_opendir)(const char *) = nullptr;
struct dirent *(*real_readdir)(DIR *) = nullptr;
struct dirent64 *(*real_readdir64)(DIR *) = nullptr;
ssize_t (*real_readlink)(const char *, char *, size_t) = nullptr;
ssize_t (*real_readlinkat)(int, const char *, char *, size_t) = nullptr;
int (*real_inotify_init)() = nullptr;
int (*real_inotify_init1)(int) = nullptr;
int (*real_add_watch)(int, const char *, uint32_t) = nullptr;
int (*real_rm_watch)(int, int) = nullptr;
ssize_t (*real_read)(int, void *, size_t) = nullptr;
ssize_t (*real_read_chk)(int, void *, size_t, size_t) = nullptr;
ssize_t (*real_readv)(int, const struct iovec *, int) = nullptr;
int (*real_close)(int) = nullptr;
int (*real_dup)(int) = nullptr;
int (*real_dup2)(int, int) = nullptr;
int (*real_dup3)(int, int, int) = nullptr;
auto &real_syscall = shield_original_syscall;

void blocked() {
    if (blockCount.fetch_add(1, std::memory_order_relaxed) < 40)
        __android_log_print(ANDROID_LOG_INFO, "ScreenshotShield", "blocked native filesystem signal");
}
std::string lower(std::string value) {
    for (char &c : value) if (c >= 'A' && c <= 'Z') c += 'a' - 'A';
    return value;
}
bool marker(const std::string &value) {
    const std::string normalized = lower(value);
    for (const char *pattern : {"screenshot", "screen_shot", "screen-shot", "screen shot",
        "screencap", "screen_capture", "screen-capture", "screen capture",
        "截屏", "截图", "螢幕截圖", "屏幕快照"})
        if (normalized.find(pattern) != std::string::npos) return true;
    return false;
}
bool shared(const std::string &path) {
    for (const char *prefix : {"/storage/", "/sdcard/", "/mnt/media_rw/", "/mnt/user/",
        "/mnt/runtime/", "/data/media/"})
        if (path.rfind(prefix, 0) == 0) return true;
    return false;
}
// Resolve relative openat paths using the descriptor rather than process cwd.
// Use the original readlink: resolving our own hooks must never recurse.
std::string resolve(int dir, const char *path) {
    InternalGuard guard;
    if (!path) return {};
    if (path[0] == '/') return path;
    char buffer[4096];
    std::string base;
    if (dir == AT_FDCWD) {
        if (getcwd(buffer, sizeof(buffer))) base = buffer;
    } else if (real_readlink) {
        std::string fd = "/proc/self/fd/" + std::to_string(dir);
        ssize_t n = real_readlink(fd.c_str(), buffer, sizeof(buffer) - 1);
        if (n >= 0) base.assign(buffer, static_cast<size_t>(n));
    }
    return base.empty() ? std::string(path) : base + "/" + path;
}
bool hidden(int dir, const char *path) {
    if (internal || !path) return false;
    InternalGuard guard;
    std::string full = resolve(dir, path);
    // If caller accesses an already-open fd through /proc, classify the destination too.
    if (full.rfind("/proc/", 0) == 0 && real_readlink) {
        char target[4096];
        ssize_t n = real_readlink(full.c_str(), target, sizeof(target));
        if (n > 0) full.assign(target, static_cast<size_t>(n));
    }
    if (shared(full) && marker(full)) return true;
    if (real_realpath) {
        char canonical[PATH_MAX];
        if (real_realpath(full.c_str(), canonical)) return shared(canonical) && marker(canonical);
    }
    return false;
}
bool hiddenFd(int fd) {
    if (internal || fd < 0 || !real_readlink) return false;
    InternalGuard guard;
    char path[4096];
    const std::string link = "/proc/self/fd/" + std::to_string(fd);
    ssize_t count = real_readlink(link.c_str(), path, sizeof(path));
    if (count <= 0) return false;
    std::string full(path, static_cast<size_t>(count));
    return shared(full) && marker(full);
}
int missing() { blocked(); errno = ENOENT; return -1; }
bool needsMode(int flags) {
    return (flags & O_CREAT) || ((flags & O_TMPFILE) == O_TMPFILE);
}
// Writes are preserved, so a scoped image editor can still save a screenshot.
bool reading(int flags) { return (flags & O_ACCMODE) != O_WRONLY; }
int h_open(const char *path, int flags, ...) {
    mode_t mode = 0;
    if (needsMode(flags)) { va_list ap; va_start(ap, flags); mode = va_arg(ap, int); va_end(ap); }
    if (reading(flags) && hidden(AT_FDCWD, path)) return missing();
    return real_open(path, flags, mode);
}
int h_openat(int dir, const char *path, int flags, ...) {
    mode_t mode = 0;
    if (needsMode(flags)) { va_list ap; va_start(ap, flags); mode = va_arg(ap, int); va_end(ap); }
    if (reading(flags) && hidden(dir, path)) return missing();
    return real_openat(dir, path, flags, mode);
}
int h_open_2(const char *path, int flags) {
    if (reading(flags) && hidden(AT_FDCWD, path)) return missing();
    return real_open_2(path, flags);
}
int h_openat_2(int dir, const char *path, int flags) {
    if (reading(flags) && hidden(dir, path)) return missing();
    return real_openat_2(dir, path, flags);
}
int h_access(const char *path, int mode) {
    if (hidden(AT_FDCWD, path)) return missing();
    return real_access(path, mode);
}
int h_faccessat(int dir, const char *path, int mode, int flags) {
    if (hidden(dir, path)) return missing();
    return real_faccessat(dir, path, mode, flags);
}
int h_stat(const char *path, struct stat *value) {
    if (hidden(AT_FDCWD, path)) return missing();
    return real_stat(path, value);
}
int h_lstat(const char *path, struct stat *value) {
    if (hidden(AT_FDCWD, path)) return missing();
    return real_lstat(path, value);
}
int h_fstatat(int dir, const char *path, struct stat *value, int flags) {
    if (hidden(dir, path) || (path && !*path && hiddenFd(dir))) return missing();
    return real_fstatat(dir, path, value, flags);
}
int h_stat64(const char *path, struct stat64 *value) {
    if (hidden(AT_FDCWD, path)) return missing();
    return real_stat64(path, value);
}
int h_lstat64(const char *path, struct stat64 *value) {
    if (hidden(AT_FDCWD, path)) return missing();
    return real_lstat64(path, value);
}
int h_fstatat64(int dir, const char *path, struct stat64 *value, int flags) {
    if (hidden(dir, path) || (path && !*path && hiddenFd(dir))) return missing();
    return real_fstatat64(dir, path, value, flags);
}
int h_fstat(int fd, struct stat *value) {
    if (hiddenFd(fd)) return missing();
    return real_fstat(fd, value);
}
int h_fstat64(int fd, struct stat64 *value) {
    if (hiddenFd(fd)) return missing();
    return real_fstat64(fd, value);
}
char *h_realpath(const char *path, char *result) {
    if (hidden(AT_FDCWD, path)) { missing(); return nullptr; }
    return real_realpath(path, result);
}
ssize_t h_pread(int fd, void *buffer, size_t size, off_t offset) {
    if (hiddenFd(fd)) return missing();
    return afterRead(fd, buffer, real_pread(fd, buffer, size, offset));
}
ssize_t h_pread64(int fd, void *buffer, size_t size, off64_t offset) {
    if (hiddenFd(fd)) return missing();
    return afterRead(fd, buffer, real_pread64(fd, buffer, size, offset));
}
ssize_t h_preadv(int fd, const struct iovec *iov, int count, off_t offset) {
    if (hiddenFd(fd)) return missing();
    return afterReadv(fd, iov, count, real_preadv(fd, iov, count, offset));
}
ssize_t h_preadv64(int fd, const struct iovec *iov, int count, off64_t offset) {
    if (hiddenFd(fd)) return missing();
    return afterReadv(fd, iov, count, real_preadv64(fd, iov, count, offset));
}
int h_statx(int dir, const char *path, int flags, unsigned int mask, struct statx *value) {
    if (hidden(dir, path) || (path && !*path && hiddenFd(dir))) return missing();
    return real_statx(dir, path, flags, mask, value);
}
void *h_mmap(void *address, size_t size, int protection, int flags, int fd, off_t offset) {
    if (!(flags & MAP_ANONYMOUS) && hiddenFd(fd)) { missing(); return MAP_FAILED; }
    return real_mmap(address, size, protection, flags, fd, offset);
}
void *h_mmap64(void *address, size_t size, int protection, int flags, int fd, off64_t offset) {
    if (!(flags & MAP_ANONYMOUS) && hiddenFd(fd)) { missing(); return MAP_FAILED; }
    return real_mmap64(address, size, protection, flags, fd, offset);
}
bool readingMode(const char *mode) { return mode && (mode[0] == 'r' || strchr(mode, '+')); }
FILE *h_fopen(const char *path, const char *mode) {
    if (readingMode(mode) && hidden(AT_FDCWD, path)) { missing(); return nullptr; }
    return real_fopen(path, mode);
}
FILE *h_freopen(const char *path, const char *mode, FILE *stream) {
    if (readingMode(mode) && hidden(AT_FDCWD, path)) { missing(); return nullptr; }
    return real_freopen(path, mode, stream);
}
DIR *h_opendir(const char *path) {
    if (hidden(AT_FDCWD, path)) { missing(); return nullptr; }
    return real_opendir(path);
}
struct dirent *h_readdir(DIR *dir) {
    struct dirent *entry;
    while ((entry = real_readdir(dir))) {
        if (!hidden(dirfd(dir), entry->d_name)) return entry;
    }
    return nullptr;
}
struct dirent64 *h_readdir64(DIR *dir) {
    struct dirent64 *entry;
    while ((entry = real_readdir64(dir))) {
        if (!hidden(dirfd(dir), entry->d_name)) return entry;
    }
    return nullptr;
}
ssize_t h_readlink(const char *path, char *buffer, size_t size) {
    if (internal) return real_readlink(path, buffer, size);
    if (hidden(AT_FDCWD, path)) return missing();
    ssize_t n = real_readlink(path, buffer, size);
    if (n > 0) {
        std::string result(buffer, static_cast<size_t>(n));
        if (shared(result) && marker(result)) return missing();
    }
    return n;
}
ssize_t h_readlinkat(int dir, const char *path, char *buffer, size_t size) {
    if (internal) return real_readlinkat(dir, path, buffer, size);
    if (hidden(dir, path)) return missing();
    ssize_t n = real_readlinkat(dir, path, buffer, size);
    if (n > 0) {
        std::string result(buffer, static_cast<size_t>(n));
        if (shared(result) && marker(result)) return missing();
    }
    return n;
}
void trackInit(int fd) {
    if (fd >= 0) { std::lock_guard lock(watchesMutex); watches[fd] = std::make_shared<WatchMap>(); }
}
void trackWatch(int fd, int wd, const char *path, uint32_t mask) {
    if (wd >= 0) {
        InternalGuard guard;
        std::string full = resolve(AT_FDCWD, path);
        char canonical[PATH_MAX];
        if (real_realpath && real_realpath(full.c_str(), canonical)) full = canonical;
        std::lock_guard lock(watchesMutex);
        auto &entry = watches[fd];
        if (!entry) entry = std::make_shared<WatchMap>();
        auto &map = *entry;
        if ((mask & IN_MASK_ADD) && map.count(wd)) map[wd].mask |= mask;
        else map[wd] = {full, mask};
    }
}
int h_inotify_init() { int fd = real_inotify_init(); trackInit(fd); return fd; }
int h_inotify_init1(int flags) { int fd = real_inotify_init1(flags); trackInit(fd); return fd; }
int h_add_watch(int fd, const char *path, uint32_t mask) {
    if (hidden(AT_FDCWD, path)) return missing();
    int wd = real_add_watch(fd, path, mask);
    trackWatch(fd, wd, path, mask);
    return wd;
}
int h_rm_watch(int fd, int wd) {
    // Keep metadata until the kernel delivers IN_IGNORED, including earlier queued events.
    return real_rm_watch(fd, wd);
}
bool tracked(int fd) {
    if (internal) return false;
    std::lock_guard lock(watchesMutex);
    return watches.count(fd);
}
size_t filterEvents(int fd, void *buffer, size_t length) {
    size_t readPosition = 0, writePosition = 0;
    std::lock_guard lock(watchesMutex);
    auto found = watches.find(fd);
    if (found == watches.end()) return length;
    auto &map = *found->second;
    auto *bytes = static_cast<char *>(buffer);
    while (readPosition + sizeof(inotify_event) <= length) {
        // Buffers passed to read need not be aligned.
        inotify_event event;
        memcpy(&event, bytes + readPosition, sizeof(event));
        size_t size = sizeof(event) + event.len;
        if (size > length - readPosition) return length; // retain malformed/unexpected data
        auto watch = map.find(event.wd);
        bool drop = false;
        if (watch != map.end() && shared(watch->second.path)) {
            std::string name;
            if (event.len) name.assign(bytes + readPosition + sizeof(event),
                strnlen(bytes + readPosition + sizeof(event), event.len));
            drop = marker(watch->second.path) || marker(name);
        }
        if (event.mask & IN_IGNORED) map.erase(event.wd);
        if (!drop) {
            memmove(bytes + writePosition, bytes + readPosition, size);
            writePosition += size;
        } else blocked();
        readPosition += size;
    }
    // A kernel inotify read returns whole events.
    return readPosition == length ? writePosition : length;
}
template <class Reader> ssize_t filteredRead(int fd, void *buffer, size_t size, Reader reader) {
    if (!tracked(fd)) return reader();
    for (;;) {
        ssize_t n = reader();
        if (n <= 0) return n;
        size_t kept = filterEvents(fd, buffer, static_cast<size_t>(n));
        if (kept) return static_cast<ssize_t>(kept);
        // Match real fd semantics: retry blocking reads, EAGAIN on drained nonblocking fds.
        // Returning 0 here would falsely signal EOF and break FileObserver's worker thread.
        if (fcntl(fd, F_GETFL) & O_NONBLOCK) { errno = EAGAIN; return -1; }
        (void) size;
    }
}
ssize_t h_read(int fd, void *buffer, size_t size) {
    if (hiddenFd(fd)) return missing();
    return afterRead(fd, buffer, filteredRead(fd, buffer, size, [&] { return real_read(fd, buffer, size); }));
}
ssize_t h_read_chk(int fd, void *buffer, size_t size, size_t capacity) {
    if (size <= capacity && hiddenFd(fd)) return missing();
    // Preserve libc's fortify abort on invalid lengths.
    return afterRead(fd, buffer, filteredRead(fd, buffer, size, [&] { return real_read_chk(fd, buffer, size, capacity); }));
}
ssize_t h_readv(int fd, const struct iovec *iov, int count) {
    if (hiddenFd(fd)) return missing();
    if (!tracked(fd) || count <= 0 || count > IOV_MAX)
        return afterReadv(fd, iov, count, real_readv(fd, iov, count));
    size_t total = 0;
    for (int i = 0; i < count; ++i) {
        if (iov[i].iov_len > SIZE_MAX - total) { errno = EINVAL; return -1; }
        total += iov[i].iov_len;
    }
    // POSIX permits partial reads; bound allocations even with a huge caller buffer.
    std::vector<char> buffer(std::min(total, size_t(1024 * 1024)));
    ssize_t n = h_read(fd, buffer.data(), buffer.size());
    if (n > 0) {
        size_t copied = 0;
        for (int i = 0; i < count && copied < static_cast<size_t>(n); ++i) {
            size_t part = std::min(iov[i].iov_len, static_cast<size_t>(n) - copied);
            memcpy(iov[i].iov_base, buffer.data() + copied, part);
            copied += part;
        }
    }
    return n;
}
int h_close(int fd) {
    int result = real_close(fd);
    if (result == 0) { std::lock_guard lock(watchesMutex); watches.erase(fd); }
    return result;
}
void copyFd(int source, int target) {
    if (target < 0 || source == target) return;
    std::lock_guard lock(watchesMutex);
    auto found = watches.find(source);
    if (found == watches.end()) watches.erase(target);
    else watches[target] = found->second;
}
int h_dup(int fd) { int n = real_dup(fd); copyFd(fd, n); return n; }
int h_dup2(int fd, int target) { int n = real_dup2(fd, target); copyFd(fd, n); return n; }
int h_dup3(int fd, int target, int flags) { int n = real_dup3(fd, target, flags); copyFd(fd, n); return n; }
int h_fcntl(int fd, int command, ...) {
    int result;
    // Bionic fcntl has no argument, integer-argument and pointer-argument variants.
    switch (command) {
        case F_GETFD: case F_GETFL: case F_GETOWN:
#ifdef F_GETSIG
        case F_GETSIG:
#endif
#ifdef F_GETLEASE
        case F_GETLEASE:
#endif
#ifdef F_GETPIPE_SZ
        case F_GETPIPE_SZ:
#endif
#ifdef F_GET_SEALS
        case F_GET_SEALS:
#endif
            result = real_fcntl(fd, command); break;
        case F_DUPFD: case F_DUPFD_CLOEXEC: case F_SETFD: case F_SETFL: case F_SETOWN:
#ifdef F_SETSIG
        case F_SETSIG:
#endif
#ifdef F_SETLEASE
        case F_SETLEASE:
#endif
#ifdef F_NOTIFY
        case F_NOTIFY:
#endif
#ifdef F_SETPIPE_SZ
        case F_SETPIPE_SZ:
#endif
#ifdef F_ADD_SEALS
        case F_ADD_SEALS:
#endif
        {
            va_list args; va_start(args, command);
            int value = va_arg(args, int); va_end(args);
            result = real_fcntl(fd, command, value); break;
        }
        default: {
            va_list args; va_start(args, command);
            void *value = va_arg(args, void *); va_end(args);
            result = real_fcntl(fd, command, value); break;
        }
    }
    if (command == F_DUPFD || command == F_DUPFD_CLOEXEC) copyFd(fd, result);
    return result;
}

struct LinuxDirent64 { uint64_t ino; int64_t offset; uint16_t reclen; uint8_t type; char name[]; };
long filterDirents(int fd, void *buffer, long length) {
    if (length <= 0) return length;
    long src = 0, dst = 0;
    auto *bytes = static_cast<char *>(buffer);
    while (src < length) {
        auto *entry = reinterpret_cast<LinuxDirent64 *>(bytes + src);
        if (entry->reclen < offsetof(LinuxDirent64, name) + 1 || entry->reclen > length - src) return length;
        auto size = entry->reclen;
        if (!hidden(fd, entry->name)) {
            memmove(bytes + dst, bytes + src, size);
            dst += size;
        } else blocked();
        src += size;
    }
    return dst;
}
// The assembly dispatcher sends only the filesystem/tracking calls here. Preserve
// all six machine-word arguments; stack-switching calls tail-jump straight to libc.
long h_syscall(long number, long a1, long a2, long a3, long a4, long a5, long a6) {
    if (!internal) {
        bool fdRead = number == SYS_read || number == SYS_readv || number == SYS_pread64;
#ifdef SYS_preadv
        fdRead |= number == SYS_preadv;
#endif
#ifdef SYS_preadv2
        fdRead |= number == SYS_preadv2;
#endif
#ifdef SYS_fstat
        fdRead |= number == SYS_fstat;
#endif
#ifdef SYS_fstat64
        fdRead |= number == SYS_fstat64;
#endif
        if (fdRead && hiddenFd(static_cast<int>(a1))) return missing();
#ifdef SYS_mmap
        if (number == SYS_mmap && hiddenFd(static_cast<int>(a5))) return missing();
#endif
#ifdef SYS_mmap2
        if (number == SYS_mmap2 && hiddenFd(static_cast<int>(a5))) return missing();
#endif
        if (number == SYS_openat && reading(static_cast<int>(a3))
            && hidden(static_cast<int>(a1), reinterpret_cast<const char *>(a2))) return missing();
        if ((number == SYS_faccessat || number == SYS_inotify_add_watch)
            && hidden(number == SYS_faccessat ? static_cast<int>(a1) : AT_FDCWD,
                reinterpret_cast<const char *>(a2))) return missing();
#ifdef SYS_newfstatat
        if (number == SYS_newfstatat && (hidden(static_cast<int>(a1),
            reinterpret_cast<const char *>(a2)) || (a2 && !*reinterpret_cast<const char *>(a2)
            && hiddenFd(static_cast<int>(a1))))) return missing();
#endif
#ifdef SYS_statx
        if (number == SYS_statx && (hidden(static_cast<int>(a1),
            reinterpret_cast<const char *>(a2)) || (a2 && !*reinterpret_cast<const char *>(a2)
            && hiddenFd(static_cast<int>(a1))))) return missing();
#endif
        bool linkRead = number == SYS_readlinkat;
#ifdef SYS_readlink
        linkRead |= number == SYS_readlink;
#endif
        if (linkRead) {
            int dir = number == SYS_readlinkat ? static_cast<int>(a1) : AT_FDCWD;
            auto path = reinterpret_cast<const char *>(number == SYS_readlinkat ? a2 : a1);
            if (hidden(dir, path)) return missing();
            long result = real_syscall(number, a1, a2, a3, a4, a5, a6);
            auto buffer = reinterpret_cast<const char *>(number == SYS_readlinkat ? a3 : a2);
            if (result > 0) {
                std::string target(buffer, static_cast<size_t>(result));
                if (shared(target) && marker(target)) return missing();
            }
            return result;
        }
        if (number == SYS_read && tracked(static_cast<int>(a1))) {
            return filteredRead(static_cast<int>(a1), reinterpret_cast<void *>(a2),
                static_cast<size_t>(a3), [&] { return real_syscall(number, a1, a2, a3, a4, a5, a6); });
        }
        if (number == SYS_readv && tracked(static_cast<int>(a1)))
            return h_readv(static_cast<int>(a1), reinterpret_cast<const iovec *>(a2), static_cast<int>(a3));
        if (number == SYS_getdents64) {
            for (;;) {
                long n = real_syscall(number, a1, a2, a3, a4, a5, a6);
                long kept = filterDirents(static_cast<int>(a1), reinterpret_cast<void *>(a2), n);
                if (kept || n <= 0) return kept;
            }
        }
    }
    long result = real_syscall(number, a1, a2, a3, a4, a5, a6);
    if (number == SYS_inotify_init1) trackInit(static_cast<int>(result));
    if (number == SYS_inotify_add_watch) trackWatch(static_cast<int>(a1), static_cast<int>(result),
        reinterpret_cast<const char *>(a2), static_cast<uint32_t>(a3));
    if (number == SYS_close && result == 0) { std::lock_guard lock(watchesMutex); watches.erase(static_cast<int>(a1)); }
#ifdef SYS_dup
    if (number == SYS_dup) copyFd(static_cast<int>(a1), static_cast<int>(result));
#endif
#ifdef SYS_dup2
    if (number == SYS_dup2) copyFd(static_cast<int>(a1), static_cast<int>(result));
#endif
#ifdef SYS_dup3
    if (number == SYS_dup3) copyFd(static_cast<int>(a1), static_cast<int>(result));
#endif
#ifdef SYS_fcntl
    if (number == SYS_fcntl && (a2 == F_DUPFD || a2 == F_DUPFD_CLOEXEC))
        copyFd(static_cast<int>(a1), static_cast<int>(result));
#endif
#ifdef SYS_fcntl64
    if (number == SYS_fcntl64 && (a2 == F_DUPFD || a2 == F_DUPFD_CLOEXEC))
        copyFd(static_cast<int>(a1), static_cast<int>(result));
#endif
    return result;
}

// Vector's symbol cache maps the complete on-disk linker as read-only MAP_SHARED.
// Some SDKs mistake that file view for the running linker when scanning /proc/maps.
// Replace only the complete shared file view, never executable/private PT_LOADs.
// mremap preserves every cached pointer and installs already-populated pages atomically.
void anonymizeLinkerFileViews() {
    struct View { uintptr_t start; size_t size; };
    std::vector<View> views;
    FILE *maps = fopen("/proc/self/maps", "r");
    if (!maps) return;
    char line[PATH_MAX + 256];
    const long pageSize = sysconf(_SC_PAGESIZE);
    while (pageSize > 0 && fgets(line, sizeof(line), maps)) {
        uintptr_t start = 0, end = 0;
        unsigned long offset = 0;
        char permissions[5]{}, path[PATH_MAX]{};
        if (sscanf(line, "%" SCNxPTR "-%" SCNxPTR " %4s %lx %*s %*s %4095s",
            &start, &end, permissions, &offset, path) != 5) continue;
        if (strcmp(permissions, "r--s") || offset || end <= start) continue;
#ifdef __LP64__
        const char *apexPath = "/apex/com.android.runtime/bin/linker64";
        const char *systemPath = "/system/bin/linker64";
#else
        const char *apexPath = "/apex/com.android.runtime/bin/linker";
        const char *systemPath = "/system/bin/linker";
#endif
        if (strcmp(path, apexPath) && strcmp(path, systemPath)) continue;
        struct stat metadata{};
        if (stat(path, &metadata) || metadata.st_size <= 0) continue;
        const size_t fileSize = static_cast<size_t>(metadata.st_size);
        const size_t rounded = (fileSize + pageSize - 1) / pageSize * pageSize;
        if (end - start != rounded || fileSize < sizeof(ElfW(Ehdr))) continue;
        const auto *header = reinterpret_cast<const ElfW(Ehdr) *>(start);
        if (memcmp(header->e_ident, ELFMAG, SELFMAG) || header->e_type != ET_DYN
            || header->e_phentsize != sizeof(ElfW(Phdr))
            || header->e_phoff > fileSize
            || header->e_phnum > (fileSize - header->e_phoff) / sizeof(ElfW(Phdr))) continue;
        const auto *programs = reinterpret_cast<const ElfW(Phdr) *>(start + header->e_phoff);
        bool executable = false;
        for (size_t i = 0; i < header->e_phnum; ++i)
            executable |= programs[i].p_type == PT_LOAD && (programs[i].p_flags & PF_X);
        if (executable) views.push_back({start, rounded});
    }
    fclose(maps);
    for (const auto &view : views) {
        void *copy = mmap(nullptr, view.size, PROT_READ | PROT_WRITE,
            MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        if (copy == MAP_FAILED) continue;
        memcpy(copy, reinterpret_cast<const void *>(view.start), view.size);
        if (mprotect(copy, view.size, PROT_READ) == 0
            && mremap(copy, view.size, view.size, MREMAP_MAYMOVE | MREMAP_FIXED,
                reinterpret_cast<void *>(view.start)) != MAP_FAILED) {
            __android_log_print(ANDROID_LOG_INFO, "ScreenshotShield",
                "linker analysis file view anonymized; address and contents retained");
        } else {
            munmap(copy, view.size);
            __android_log_print(ANDROID_LOG_WARN, "ScreenshotShield",
                "linker analysis file view replacement failed");
        }
    }
}
size_t symbolSize(void *address, const char *name) {
    Dl_info info{};
    if (!dladdr(address, &info) || !info.dli_fbase) return 0;
    auto base = reinterpret_cast<uintptr_t>(info.dli_fbase);
    auto *header = reinterpret_cast<const ElfW(Ehdr) *>(base);
    auto *programs = reinterpret_cast<const ElfW(Phdr) *>(base + header->e_phoff);
    const ElfW(Dyn) *dynamic = nullptr;
    for (size_t i = 0; i < header->e_phnum; ++i) {
        if (programs[i].p_type == PT_DYNAMIC) dynamic =
            reinterpret_cast<const ElfW(Dyn) *>(base + programs[i].p_vaddr);
    }
    if (!dynamic) return 0;
    const ElfW(Sym) *symbols = nullptr;
    const char *strings = nullptr;
    const uint32_t *gnuHash = nullptr;
    size_t count = 0, stringSize = 0;
    auto pointer = [base](ElfW(Addr) value) { return value >= base ? value : base + value; };
    for (auto *entry = dynamic; entry->d_tag != DT_NULL; ++entry) {
        switch (entry->d_tag) {
            case DT_SYMTAB: symbols = reinterpret_cast<const ElfW(Sym) *>(pointer(entry->d_un.d_ptr)); break;
            case DT_STRTAB: strings = reinterpret_cast<const char *>(pointer(entry->d_un.d_ptr)); break;
            case DT_STRSZ: stringSize = entry->d_un.d_val; break;
            case DT_HASH: count = reinterpret_cast<const uint32_t *>(pointer(entry->d_un.d_ptr))[1]; break;
            case DT_GNU_HASH: gnuHash = reinterpret_cast<const uint32_t *>(pointer(entry->d_un.d_ptr)); break;
            default: break;
        }
    }
    if (!symbols || !strings) return 0;
    if (!count && gnuHash) {
        uint32_t offset = gnuHash[1];
        auto *buckets = reinterpret_cast<const uint32_t *>(
            reinterpret_cast<const ElfW(Addr) *>(gnuHash + 4) + gnuHash[2]);
        uint32_t last = offset;
        for (uint32_t i = 0; i < gnuHash[0]; ++i) last = std::max(last, buckets[i]);
        if (last >= offset) {
            auto *chains = buckets + gnuHash[0];
            count = last;
            while (count < 1000000 && !(chains[count++ - offset] & 1)) {}
        }
    }
    if (count > 1000000) return 0;
    for (size_t i = 0; i < count; ++i) {
        if (symbols[i].st_name < stringSize && !strcmp(strings + symbols[i].st_name, name))
            return symbols[i].st_size;
    }
    return 0;
}
bool existingExternalRedirect(void *symbol) {
#if defined(__aarch64__)
    uint32_t words[2];
    memcpy(words, symbol, sizeof(words));
    uintptr_t target = 0;
    // A packer may already own this entry. Chaining another inline hook can
    // re-enter its guard indefinitely. Recognize redirects, not package names.
    if ((words[0] & 0xfc000000u) == 0x14000000u) {
        int64_t offset = static_cast<int64_t>(words[0] & 0x03ffffffu);
        if (offset & 0x02000000) offset -= 0x04000000;
        target = reinterpret_cast<uintptr_t>(symbol) + offset * 4;
    } else if ((words[0] & 0xffffffe0u) == 0x58000040u
        && (words[1] & 0xfffffc1fu) == 0xd61f0000u
        && (words[0] & 31u) == ((words[1] >> 5) & 31u)) {
        // LDR Xn, [PC + 8]; BR Xn; .quad target (16-byte absolute detour).
        memcpy(&target, static_cast<const char *>(symbol) + 8, sizeof(target));
    }
    if (!target) return false;
    Dl_info source{}, destination{};
    if (!dladdr(symbol, &source) || !source.dli_fbase) return false;
    return !dladdr(reinterpret_cast<void *>(target), &destination)
        || destination.dli_fbase != source.dli_fbase;
#else
    (void) symbol;
    return false;
#endif
}
template <class R, class O> void install(const NativeAPIEntries *api, void *lib, const char *name, R replacement, O *original) {
    void *symbol = dlsym(lib, name);
    if (!symbol) return;
    // Vector/Dobby can emit a 16-byte redirect. A shorter Bionic wrapper may sit directly
    // against the next function (e.g. Android 16 inotify_init -> ioctl). Never overwrite it.
    if (symbolSize(symbol, name) < 16) {
        __android_log_print(ANDROID_LOG_INFO, "ScreenshotShield", "short native wrapper skipped: %s", name);
        return;
    }
    // A previously installed alias now redirects to us. Do not mistake it for
    // an application's pre-existing hook or assign that alias our patched entry.
    if (hookedSymbols.count(symbol)) return;
    if (existingExternalRedirect(symbol)) {
        if (!*original) *original = reinterpret_cast<O>(symbol);
        __android_log_print(ANDROID_LOG_WARN, "ScreenshotShield",
            "existing native redirect retained: %s", name);
        return;
    }
    // Bionic aliases often share addresses. Never hook one address twice.
    if (!hookedSymbols.insert(symbol).second) return;
    if (api->hookFunc(symbol, reinterpret_cast<void *>(replacement),
        reinterpret_cast<void **>(original)) == 0) {
        successfulHooks.insert(symbol);
        hookCount++;
    }
    else __android_log_print(ANDROID_LOG_WARN, "ScreenshotShield", "native hook failed: %s", name);
}
} // namespace
extern "C" __attribute__((visibility("default"))) bool
appstateshield_set_selinux_read_filter(void *symbol, ReadFilter filter) {
    if (!successfulHooks.count(symbol)) return false;
    extraReadFilter.store(filter);
    return true;
}

extern "C" __attribute__((visibility("hidden"))) long shield_filtered_syscall(
    long number, long a1, long a2, long a3, long a4, long a5, long a6) {
    return h_syscall(number, a1, a2, a3, a4, a5, a6);
}

extern "C" __attribute__((visibility("default"))) OnLoad native_init(const NativeAPIEntries *api) {
    if (!api || api->version < 1 || !api->hookFunc) return nullptr;
    internal = true;
    anonymizeLinkerFileViews();
    // Vector invokes native_init while holding its dlopen registry mutex.
    // libc is already loaded; calling dlopen here would re-enter and deadlock that mutex.
    void *lib = RTLD_DEFAULT;
    // Resolve readlink before any path hook is active.
    real_readlink = reinterpret_cast<decltype(real_readlink)>(dlsym(lib, "readlink"));
    real_realpath = reinterpret_cast<decltype(real_realpath)>(dlsym(lib, "realpath"));
#define INSTALL(name, replacement, original) install(api, lib, name, replacement, &original)
    INSTALL("readlink", h_readlink, real_readlink);
    INSTALL("readlinkat", h_readlinkat, real_readlinkat);
    INSTALL("realpath", h_realpath, real_realpath);
    INSTALL("open", h_open, real_open);
    INSTALL("open64", h_open, real_open);
    INSTALL("openat", h_openat, real_openat);
    INSTALL("openat64", h_openat, real_openat);
    INSTALL("__open_2", h_open_2, real_open_2);
    INSTALL("__openat_2", h_openat_2, real_openat_2);
    INSTALL("access", h_access, real_access);
    INSTALL("faccessat", h_faccessat, real_faccessat);
    INSTALL("stat", h_stat, real_stat);
    INSTALL("lstat", h_lstat, real_lstat);
    INSTALL("fstatat", h_fstatat, real_fstatat);
    INSTALL("stat64", h_stat64, real_stat64);
    INSTALL("lstat64", h_lstat64, real_lstat64);
    INSTALL("fstatat64", h_fstatat64, real_fstatat64);
    INSTALL("fstat", h_fstat, real_fstat);
    INSTALL("fstat64", h_fstat64, real_fstat64);
    INSTALL("pread", h_pread, real_pread);
    INSTALL("pread64", h_pread64, real_pread64);
    INSTALL("preadv", h_preadv, real_preadv);
    INSTALL("preadv64", h_preadv64, real_preadv64);
    INSTALL("statx", h_statx, real_statx);
    INSTALL("mmap", h_mmap, real_mmap);
    INSTALL("mmap64", h_mmap64, real_mmap64);
    INSTALL("fopen", h_fopen, real_fopen);
    INSTALL("fopen64", h_fopen, real_fopen);
    INSTALL("freopen", h_freopen, real_freopen);
    INSTALL("freopen64", h_freopen, real_freopen);
    INSTALL("opendir", h_opendir, real_opendir);
    INSTALL("readdir", h_readdir, real_readdir);
    INSTALL("readdir64", h_readdir64, real_readdir64);
    INSTALL("inotify_init", h_inotify_init, real_inotify_init);
    INSTALL("inotify_init1", h_inotify_init1, real_inotify_init1);
    INSTALL("inotify_add_watch", h_add_watch, real_add_watch);
    INSTALL("inotify_rm_watch", h_rm_watch, real_rm_watch);
    INSTALL("read", h_read, real_read);
    INSTALL("__read_chk", h_read_chk, real_read_chk);
    INSTALL("readv", h_readv, real_readv);
    INSTALL("close", h_close, real_close);
    INSTALL("dup", h_dup, real_dup);
    INSTALL("dup2", h_dup2, real_dup2);
    INSTALL("dup3", h_dup3, real_dup3);
    INSTALL("fcntl", h_fcntl, real_fcntl);
    INSTALL("fcntl64", h_fcntl, real_fcntl);
    INSTALL("syscall", shield_syscall_dispatch, real_syscall);
#undef INSTALL
    internal = false;
    __android_log_print(ANDROID_LOG_INFO, "ScreenshotShield", "native ready api=%u hooks=%d",
        api->version, hookCount.load());
    return nullptr;
}
extern "C" __attribute__((visibility("default"))) jint JNI_OnLoad(JavaVM *, void *) {
    return JNI_VERSION_1_6;
}
