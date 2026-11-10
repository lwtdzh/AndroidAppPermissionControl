#include <jni.h>
#include <android/binder_ibinder.h>
#include <android/binder_ibinder_jni.h>
#include <dlfcn.h>
#include <dirent.h>
#include <fcntl.h>
#include <sys/inotify.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/uio.h>
#include <unistd.h>
#include <cerrno>
#include <cstdint>
#include <map>
#include <string>
#include <vector>

namespace {
std::string text(JNIEnv* env, jstring value) {
    const char* chars = env->GetStringUTFChars(value, nullptr);
    std::string result(chars);
    env->ReleaseStringUTFChars(value, chars);
    return result;
}
jobjectArray array(JNIEnv* env, const std::vector<std::string>& values) {
    jclass type = env->FindClass("java/lang/String");
    auto result = env->NewObjectArray(values.size(), type, nullptr);
    for (size_t i = 0; i < values.size(); i++) {
        jstring value = env->NewStringUTF(values[i].c_str());
        env->SetObjectArrayElement(result, i, value);
        env->DeleteLocalRef(value);
    }
    env->DeleteLocalRef(type);
    return result;
}
struct Watch { int fd; std::map<int, std::string> paths; };
struct Entry { uint64_t ino; int64_t off; unsigned short length; unsigned char type; char name[1]; };
}

extern "C" JNIEXPORT jobject JNICALL
Java_io_github_lwtdzh_screenshotdetector_Native_activityTask(JNIEnv* env, jclass) {
    void* library = dlopen("libbinder_ndk.so", RTLD_NOW | RTLD_LOCAL);
    if (!library) return nullptr;
    auto check = reinterpret_cast<AIBinder* (*)(const char*)>(dlsym(library, "AServiceManager_checkService"));
    auto toJava = reinterpret_cast<jobject (*)(JNIEnv*, AIBinder*)>(dlsym(library, "AIBinder_toJavaBinder"));
    auto release = reinterpret_cast<void (*)(AIBinder*)>(dlsym(library, "AIBinder_decStrong"));
    jobject result = nullptr;
    if (check && toJava && release) {
        AIBinder* binder = check("activity_task");
        if (binder) { result = toJava(env, binder); release(binder); }
    }
    dlclose(library);
    return result;
}
extern "C" JNIEXPORT jobjectArray JNICALL
Java_io_github_lwtdzh_screenshotdetector_Native_files(JNIEnv* env, jclass, jstring dir, jboolean raw) {
    std::string root = text(env, dir);
    std::vector<std::string> result;
    auto add = [&](const char* name) {
        if (name[0] == '.') return;
        std::string path = root + "/" + name;
        if (raw) {
            struct statx st{};
            if (syscall(SYS_statx, AT_FDCWD, path.c_str(), 0, STATX_TYPE | STATX_SIZE, &st) == 0
                && S_ISREG(st.stx_mode) && st.stx_size > 0) result.push_back(path);
        } else {
            struct stat st{};
            if (stat(path.c_str(), &st) == 0 && S_ISREG(st.st_mode) && st.st_size > 0) result.push_back(path);
        }
    };
    if (!raw) {
        DIR* stream = opendir(root.c_str());
        if (!stream) return nullptr;
        while (auto entry = readdir(stream)) add(entry->d_name);
        closedir(stream);
    } else {
        int fd = static_cast<int>(syscall(SYS_openat, AT_FDCWD, root.c_str(), O_RDONLY | O_DIRECTORY, 0));
        if (fd < 0) return nullptr;
        alignas(8) char buffer[8192];
        long size;
        while ((size = syscall(SYS_getdents64, fd, buffer, sizeof(buffer))) > 0) {
            for (long offset = 0; offset < size;) {
                auto entry = reinterpret_cast<Entry*>(buffer + offset);
                if (entry->length < 20 || offset + entry->length > size) break;
                add(entry->name); offset += entry->length;
            }
        }
        close(fd);
        if (size < 0) return nullptr;
    }
    return array(env, result);
}
extern "C" JNIEXPORT jlong JNICALL
Java_io_github_lwtdzh_screenshotdetector_Native_watch(JNIEnv* env, jclass, jobjectArray dirs) {
    int original = inotify_init1(IN_NONBLOCK | IN_CLOEXEC);
    if (original < 0) return 0;
    // Exercise fcntl duplication before adding watches, matching a real alternate fd route.
    int fd = fcntl(original, F_DUPFD_CLOEXEC, 0);
    close(original);
    if (fd < 0) return 0;
    auto watch = new Watch{fd, {}};
    for (int i = 0; i < env->GetArrayLength(dirs); i++) {
        auto dir = static_cast<jstring>(env->GetObjectArrayElement(dirs, i));
        auto path = text(env, dir); env->DeleteLocalRef(dir);
        int wd = inotify_add_watch(fd, path.c_str(), IN_CLOSE_WRITE | IN_MOVED_TO | IN_CREATE);
        if (wd >= 0) watch->paths[wd] = path;
    }
    if (watch->paths.empty()) { close(fd); delete watch; return 0; }
    return reinterpret_cast<jlong>(watch);
}
extern "C" JNIEXPORT jobjectArray JNICALL
Java_io_github_lwtdzh_screenshotdetector_Native_events(JNIEnv* env, jclass, jlong handle) {
    auto watch = reinterpret_cast<Watch*>(handle);
    std::vector<std::string> result;
    alignas(inotify_event) char buffer[16384];
    ssize_t size;
    while ((size = read(watch->fd, buffer, sizeof(buffer))) > 0) {
        for (size_t offset = 0; offset + sizeof(inotify_event) <= static_cast<size_t>(size);) {
            auto event = reinterpret_cast<inotify_event*>(buffer + offset);
            size_t length = sizeof(inotify_event) + event->len;
            if (offset + length > static_cast<size_t>(size)) break;
            auto path = watch->paths.find(event->wd);
            if (path != watch->paths.end() && event->len && !(event->mask & IN_ISDIR))
                result.push_back(path->second + "/" + event->name);
            offset += length;
        }
    }
    return array(env, result);
}
extern "C" JNIEXPORT void JNICALL
Java_io_github_lwtdzh_screenshotdetector_Native_close(JNIEnv*, jclass, jlong handle) {
    auto watch = reinterpret_cast<Watch*>(handle);
    if (watch) { close(watch->fd); delete watch; }
}
extern "C" JNIEXPORT jint JNICALL
Java_io_github_lwtdzh_screenshotdetector_Native_descriptor(JNIEnv*, jclass, jint fd) {
    int mask = 0;
    std::string alias = "/proc/self/fd/" + std::to_string(fd);
    int reopened = open(alias.c_str(), O_RDONLY);
    if (reopened >= 0) { mask |= 1; close(reopened); }
    struct stat st{};
    if (stat(alias.c_str(), &st) == 0) mask |= 2;
    char byte = 0;
    if (read(fd, &byte, 1) == 1) mask |= 4;
    if (pread(fd, &byte, 1, 0) == 1) mask |= 8;
    iovec vec{&byte, 1};
    if (readv(fd, &vec, 1) == 1) mask |= 16;
    void* mapping = mmap(nullptr, 1, PROT_READ, MAP_PRIVATE, fd, 0);
    if (mapping != MAP_FAILED) { mask |= 32; munmap(mapping, 1); }
    int copy = fcntl(fd, F_DUPFD_CLOEXEC, 0);
    if (copy >= 0) {
        if (pread(copy, &byte, 1, 0) == 1) mask |= 64;
        close(copy);
    }
    if (fstat(fd, &st) == 0) mask |= 128;
    struct statx sx{};
    if (syscall(SYS_statx, fd, "", AT_EMPTY_PATH, STATX_SIZE, &sx) == 0) mask |= 256;
    return mask;
}
