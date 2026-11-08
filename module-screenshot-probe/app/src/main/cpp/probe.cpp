#include <jni.h>
#include <dirent.h>
#include <fcntl.h>
#include <sys/inotify.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/uio.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <dlfcn.h>
#include <unistd.h>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <cstdint>
#include <string>
#include <vector>

#if defined(__aarch64__) || defined(__x86_64__)
extern "C" long probe_clone_new_stack(void *stackTop);
#endif

namespace {
int watchFd = -1;
bool readable(const char *path, bool raw) {
    int fd = raw ? static_cast<int>(syscall(SYS_openat, AT_FDCWD, path, O_RDONLY, 0))
        : open(path, O_RDONLY);
    if (fd < 0) return false;
    close(fd);
    return true;
}
bool stdioReadable(const char *path) {
    FILE *stream = fopen(path, "r");
    if (!stream) return false;
    fclose(stream);
    return true;
}
// A test-only kernel open provides the same input as a descriptor received from an
// unscoped process. It deliberately bypasses libc; it is NOT a claimed protected route.
int fixtureFd(const char *path) {
#ifdef __aarch64__
    register long x0 asm("x0") = AT_FDCWD;
    register long x1 asm("x1") = reinterpret_cast<long>(path);
    register long x2 asm("x2") = O_RDONLY;
    register long x3 asm("x3") = 0;
    register long x8 asm("x8") = SYS_openat;
    asm volatile("svc 0" : "+r"(x0) : "r"(x1), "r"(x2), "r"(x3), "r"(x8) : "memory");
    return static_cast<int>(x0);
#else
    return open(path, O_RDONLY);
#endif
}
struct LinuxDirent64 { uint64_t ino; int64_t off; uint16_t size; uint8_t type; char name[]; };
std::string boolean(bool value) { return value ? "true" : "false"; }
bool cloneNewStack() {
#if defined(__aarch64__) || defined(__x86_64__)
    constexpr size_t size = 65536;
    void *stack = mmap(nullptr, size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (stack == MAP_FAILED) return false;
    long child = probe_clone_new_stack(static_cast<char *>(stack) + size);
    int status = 0;
    pid_t waited;
    do { waited = child > 0 ? waitpid(static_cast<pid_t>(child), &status, 0) : -1; }
    while (waited < 0 && errno == EINTR);
    munmap(stack, size);
    return waited == child && child > 0 && WIFEXITED(status) && WEXITSTATUS(status) == 0;
#else
    return false;
#endif
}
bool syscallSixArguments() {
    const long page = sysconf(_SC_PAGESIZE);
    if (page <= 0) return false;
    char filename[] = "/data/data/io.github.lwtdzh.screenshotprobe/cache/mmap-XXXXXX";
    int fd = mkstemp(filename);
    if (fd < 0) return false;
    unlink(filename);
    const char first = 'A', second = 'B';
    bool prepared = ftruncate(fd, page * 2) == 0
        && pwrite(fd, &first, 1, 0) == 1 && pwrite(fd, &second, 1, page) == 1;
    // A nonzero file offset exercises argument six of the filtered mmap syscall.
    long result = prepared ? syscall(SYS_mmap, nullptr, page, PROT_READ, MAP_PRIVATE, fd, page) : -1;
    bool okay = result != -1 && *reinterpret_cast<const char *>(result) == second;
    if (result != -1) munmap(reinterpret_cast<void *>(result), page);
    close(fd);
    return okay;
}
}
extern "C" JNIEXPORT jstring JNICALL
Java_io_github_lwtdzh_screenshotprobe_ProbeActivity_nativeChecks(
    JNIEnv *env, jclass, jstring directory, jstring screenshot, jstring ordinary) {
    const char *dir = env->GetStringUTFChars(directory, nullptr);
    const char *shot = env->GetStringUTFChars(screenshot, nullptr);
    const char *photo = env->GetStringUTFChars(ordinary, nullptr);
    struct stat metadata;
    std::string json = "{\"clone_new_stack_supported\":"
#if defined(__aarch64__) || defined(__x86_64__)
        + boolean(true)
#else
        + boolean(false)
#endif
        + ",\"clone_new_stack_ok\":" + boolean(cloneNewStack())
        + ",\"syscall_getpid_ok\":" + boolean(syscall(SYS_getpid) == getpid())
        + ",\"syscall_six_arguments_ok\":" + boolean(syscallSixArguments())
        + ",\"open_screenshot\":" + boolean(readable(shot, false))
        + ",\"open_normal\":" + boolean(readable(photo, false))
        + ",\"syscall_open_screenshot\":" + boolean(readable(shot, true))
        + ",\"syscall_open_normal\":" + boolean(readable(photo, true))
        + ",\"stat_screenshot\":" + boolean(stat(shot, &metadata) == 0)
        + ",\"stat_normal\":" + boolean(stat(photo, &metadata) == 0)
        + ",\"access_screenshot\":" + boolean(access(shot, R_OK) == 0)
        + ",\"access_normal\":" + boolean(access(photo, R_OK) == 0)
        + ",\"fopen_screenshot\":" + boolean(stdioReadable(shot))
        + ",\"fopen_normal\":" + boolean(stdioReadable(photo));
    for (bool screenshot : {true, false}) {
        const std::string suffix = screenshot ? "_screenshot" : "_normal";
        int fd = fixtureFd(screenshot ? shot : photo);
        char bytes[32];
        iovec vector{bytes, sizeof(bytes)};
        json += ",\"fixture_fd" + suffix + "\":" + boolean(fd >= 0);
        json += ",\"fd_read" + suffix + "\":" + boolean(read(fd, bytes, 1) > 0);
        json += ",\"fd_pread" + suffix + "\":" + boolean(pread(fd, bytes, 1, 0) > 0);
        json += ",\"fd_readv" + suffix + "\":" + boolean(readv(fd, &vector, 1) > 0);
        json += ",\"fd_preadv" + suffix + "\":" + boolean(preadv(fd, &vector, 1, 0) > 0);
        json += ",\"fd_fstat" + suffix + "\":" + boolean(fstat(fd, &metadata) == 0);
        json += ",\"fd_syscall_read" + suffix + "\":" + boolean(syscall(SYS_read, fd, bytes, 1) > 0);
        void *mapped = mmap(nullptr, 4096, PROT_READ, MAP_PRIVATE, fd, 0);
        json += ",\"fd_mmap" + suffix + "\":" + boolean(mapped != MAP_FAILED);
        if (mapped != MAP_FAILED) munmap(mapped, 4096);
        int alias = fcntl(fd, F_DUPFD_CLOEXEC, 0);
        json += ",\"fd_dup_pread" + suffix + "\":" + boolean(pread(alias, bytes, 1, 0) > 0);
        std::string proc = "/proc/self/fd/" + std::to_string(fd);
        char linkTarget[4096];
        json += ",\"procfd_syscall_readlink" + suffix + "\":" + boolean(
            syscall(SYS_readlinkat, AT_FDCWD, proc.c_str(), linkTarget, sizeof(linkTarget)) > 0);
        json += ",\"procfd_open" + suffix + "\":" + boolean(readable(proc.c_str(), false));
        char resolved[4096];
        json += ",\"procfd_realpath" + suffix + "\":" + boolean(realpath(proc.c_str(), resolved) != nullptr);
        std::string root = std::string("/proc/self/root") + (screenshot ? shot : photo);
        json += ",\"procroot_open" + suffix + "\":" + boolean(readable(root.c_str(), false));
        std::string link = "/data/data/io.github.lwtdzh.screenshotprobe/files/" + suffix;
        unlink(link.c_str());
        symlink(screenshot ? shot : photo, link.c_str());
        json += ",\"symlink_open" + suffix + "\":" + boolean(readable(link.c_str(), false));
        using Statx = int (*)(int, const char *, int, unsigned int, void *);
        auto statx = reinterpret_cast<Statx>(dlsym(RTLD_DEFAULT, "statx"));
        alignas(64) char statxBuffer[512];
        json += ",\"libc_statx" + suffix + "\":" + boolean(
            statx && statx(AT_FDCWD, screenshot ? shot : photo, 0, 0x7ff, statxBuffer) == 0);
#ifdef SYS_statx
        json += ",\"fd_syscall_statx" + suffix + "\":" + boolean(
            syscall(SYS_statx, fd, "", AT_EMPTY_PATH, 0x7ff, statxBuffer) == 0);
#endif
        unlink(link.c_str());
        if (alias >= 0) close(alias);
        if (fd >= 0) close(fd);
    }
    int dirfd = open(dir, O_RDONLY | O_DIRECTORY);
    int shotfd = openat(dirfd, "Screenshot_probe.png", O_RDONLY);
    int photofd = openat(dirfd, "ordinary_probe.png", O_RDONLY);
    json += ",\"openat_screenshot\":" + boolean(shotfd >= 0)
        + ",\"openat_normal\":" + boolean(photofd >= 0);
    if (shotfd >= 0) close(shotfd);
    if (photofd >= 0) close(photofd);
    if (dirfd >= 0) close(dirfd);
    int rawDirectory = static_cast<int>(syscall(SYS_openat, AT_FDCWD, dir, O_RDONLY | O_DIRECTORY, 0));
    bool rawShot = false, rawNormal = false;
    if (rawDirectory >= 0) {
        alignas(LinuxDirent64) char bytes[8192];
        long count;
        while ((count = syscall(SYS_getdents64, rawDirectory, bytes, sizeof(bytes))) > 0) {
            for (long offset = 0; offset < count;) {
                auto *entry = reinterpret_cast<LinuxDirent64 *>(bytes + offset);
                if (strstr(entry->name, "Screenshot_probe")) rawShot = true;
                if (strstr(entry->name, "ordinary_probe")) rawNormal = true;
                offset += entry->size;
            }
        }
        close(rawDirectory);
    }
    json += ",\"syscall_getdents_screenshot\":" + boolean(rawShot)
        + ",\"syscall_getdents_normal\":" + boolean(rawNormal);
#ifdef SYS_newfstatat
    json += ",\"syscall_stat_screenshot\":" + boolean(syscall(SYS_newfstatat, AT_FDCWD, shot, &metadata, 0) == 0)
        + ",\"syscall_stat_normal\":" + boolean(syscall(SYS_newfstatat, AT_FDCWD, photo, &metadata, 0) == 0);
#endif
    bool listedShot = false, listedNormal = false;
    DIR *stream = opendir(dir);
    if (stream) {
        while (dirent *entry = readdir(stream)) {
            if (strstr(entry->d_name, "Screenshot_probe")) listedShot = true;
            if (strstr(entry->d_name, "ordinary_probe")) listedNormal = true;
        }
        closedir(stream);
    }
    json += ",\"readdir_screenshot\":" + boolean(listedShot)
        + ",\"readdir_normal\":" + boolean(listedNormal) + "}";
    env->ReleaseStringUTFChars(directory, dir);
    env->ReleaseStringUTFChars(screenshot, shot);
    env->ReleaseStringUTFChars(ordinary, photo);
    return env->NewStringUTF(json.c_str());
}
extern "C" JNIEXPORT void JNICALL
Java_io_github_lwtdzh_screenshotprobe_ProbeActivity_startWatch(JNIEnv *env, jclass, jstring directory) {
    if (watchFd >= 0) close(watchFd);
    const char *dir = env->GetStringUTFChars(directory, nullptr);
    watchFd = inotify_init1(IN_NONBLOCK | IN_CLOEXEC);
    // Duplicate before adding the watch, then read only from the alias after closing the original.
    // A copied (rather than shared) descriptor map would leak the screenshot events here.
    int alias = fcntl(watchFd, F_DUPFD_CLOEXEC, 0);
    inotify_add_watch(watchFd, dir, IN_CREATE | IN_CLOSE_WRITE | IN_MOVED_TO);
    if (alias >= 0) { close(watchFd); watchFd = alias; }
    env->ReleaseStringUTFChars(directory, dir);
}
extern "C" JNIEXPORT jstring JNICALL
Java_io_github_lwtdzh_screenshotprobe_ProbeActivity_drainWatch(JNIEnv *env, jclass) {
    int screenshots = 0, ordinary = 0;
    alignas(inotify_event) char bytes[8192];
    ssize_t n;
    while ((n = read(watchFd, bytes, sizeof(bytes))) > 0) {
        for (size_t position = 0; position + sizeof(inotify_event) <= static_cast<size_t>(n);) {
            auto *event = reinterpret_cast<inotify_event *>(bytes + position);
            if (event->len) {
                if (strstr(event->name, "Screenshot")) screenshots++;
                else ordinary++;
            }
            position += sizeof(inotify_event) + event->len;
        }
    }
    std::string json = "{\"screenshot_events\":" + std::to_string(screenshots)
        + ",\"normal_events\":" + std::to_string(ordinary)
        + ",\"drain_errno\":" + std::to_string(errno) + "}";
    return env->NewStringUTF(json.c_str());
}
extern "C" JNIEXPORT void JNICALL
Java_io_github_lwtdzh_screenshotprobe_ProbeActivity_stopWatch(JNIEnv *, jclass) {
    if (watchFd >= 0) close(watchFd);
    watchFd = -1;
}
