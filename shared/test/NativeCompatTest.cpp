#include <dlfcn.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <sys/uio.h>
#include <sys/wait.h>
#include <unistd.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cerrno>
#include <cstdint>
#include "../native/elf-code-view.h"

void require(bool ok, const char *name) {
    if (!ok) { fprintf(stderr, "FAIL %s errno=%d\n", name, errno); exit(1); }
    printf("PASS %s\n", name);
}
long rawRead(pid_t pid, const iovec *l, size_t lc, const iovec *r, size_t rc) {
#if defined(__aarch64__)
    register long x8 asm("x8") = __NR_process_vm_readv;
    register long x0 asm("x0") = pid, x1 asm("x1") = reinterpret_cast<long>(l), x2 asm("x2") = lc;
    register long x3 asm("x3") = reinterpret_cast<long>(r), x4 asm("x4") = rc, x5 asm("x5") = 0;
    asm volatile("svc #0" : "+r"(x0) : "r"(x8), "r"(x1), "r"(x2), "r"(x3), "r"(x4), "r"(x5) : "memory", "cc");
    return x0;
#else
    return -ENOSYS;
#endif
}
int main(int argc, char **argv) {
    require(argc == 2, "fixture directory");
    setvbuf(stdout, nullptr, _IONBF, 0);
    auto load = [&](const char *name) {
        char path[4096];
        snprintf(path, sizeof(path), "%s/%s", argv[1], name);
        void *lib = dlopen(path, RTLD_NOW | RTLD_GLOBAL);
        if (!lib) fprintf(stderr, "%s\n", dlerror());
        require(lib != nullptr, name);
        return lib;
    };
    void *vector = load("libcompatvector.so"), *art = load("libart.so");
    void *entry = reinterpret_cast<void *(*)()>(dlsym(art, "fixtureEntry"))();
    void *target = dlsym(vector, "vectorReplacement");
    require(dlsym(art, "registerNativeFixture") == nullptr, "ART fixture symbol is local");
    uint32_t before[4], installed[4];
    memcpy(before, entry, sizeof(before));
    uintptr_t pc = reinterpret_cast<uintptr_t>(entry), to = reinterpret_cast<uintptr_t>(target);
    int64_t delta = static_cast<int64_t>(to & ~uintptr_t(4095)) - static_cast<int64_t>(pc & ~uintptr_t(4095));
    require(delta >= -(1ll << 32) && delta < (1ll << 32), "ADRP fixture range");
    uint32_t pages = static_cast<uint32_t>(delta / 4096) & 0x1fffffu;
    installed[0] = 0x90000011u | ((pages & 3) << 29) | ((pages >> 2) << 5);
    installed[1] = 0x91000231u | ((to & 4095u) << 10);
    installed[2] = 0xd61f0220u;
    installed[3] = before[3];
    auto patch = [&](const uint32_t *words) {
        long page = sysconf(_SC_PAGESIZE);
        void *start = reinterpret_cast<void *>(pc & ~(uintptr_t(page) - 1));
        require(mprotect(start, page, PROT_READ | PROT_WRITE | PROT_EXEC) == 0, "fixture writable");
        memcpy(entry, words, 16);
        __builtin___clear_cache(static_cast<char *>(entry), static_cast<char *>(entry) + 16);
        require(mprotect(start, page, PROT_READ | PROT_EXEC) == 0, "fixture executable");
    };
    patch(installed);
    require(shield_code::arm64Redirect(pc, installed) == to, "decode live ADRP ADD BR");
    require(reinterpret_cast<long (*)()>(entry)() == 91, "Vector fixture hook executes");
    void *compat = load("libnativecompat.so");
    auto prepare = reinterpret_cast<unsigned char (*)(void *, void *)>(dlsym(compat,
        "Java_io_github_lwtdzh_appstateshield_NativeLibraries_prepare"));
    auto finish = reinterpret_cast<void (*)(void *, void *)>(dlsym(compat,
        "Java_io_github_lwtdzh_appstateshield_NativeLibraries_finish"));
    require(prepare && finish && prepare(nullptr, nullptr), "production compatibility prepare");
    finish(nullptr, nullptr);
    uint8_t bytes[32]{};
    iovec l{bytes, 16}, r{entry, 16};
    require(rawRead(getpid(), &l, 1, &r, 1) == 16 && !memcmp(bytes, installed, 16),
        "direct syscall retains actual hooked instructions");
    require(syscall(__NR_process_vm_readv, getpid(), &l, 1, &r, 1, 0) == 16
        && !memcmp(bytes, before, 16), "libc syscall code view matches disk");
    require(process_vm_readv(getpid(), &l, 1, &r, 1, 0) == 16
        && !memcmp(bytes, before, 16), "named process_vm_readv matches disk");
    require(reinterpret_cast<long (*)()>(entry)() == 91, "read view preserves Vector execution");
    iovec ls[] = {{bytes, 3}, {bytes + 3, 0}, {bytes + 3, 13}};
    iovec rs[] = {{entry, 5}, {static_cast<char *>(entry) + 5, 11}};
    require(process_vm_readv(getpid(), ls, 3, rs, 2, 0) == 16 && !memcmp(bytes, before, 16),
        "different scatter gather splits and zero length");
    l.iov_len = 32;
    memset(bytes, 0xa5, sizeof(bytes));
    require(process_vm_readv(getpid(), &l, 1, &r, 1, 0) == 16 && !memcmp(bytes, before, 16)
        && bytes[16] == 0xa5, "only returned bytes are changed");
    l.iov_len = 16;
    iovec partial[] = {{entry, 16}, {reinterpret_cast<void *>(1), 16}};
    require(process_vm_readv(getpid(), &l, 1, partial, 2, 0) == 16 && !memcmp(bytes, before, 16),
        "partial remote read preserves returned count");
    errno = 0;
    require(process_vm_readv(getpid(), reinterpret_cast<iovec *>(1), 1, &r, 1, 0) == -1
        && errno == EFAULT, "invalid iovec preserves EFAULT");
    errno = 0;
    require(process_vm_readv(getpid(), &l, 1025, &r, 1, 0) == -1 && errno == EINVAL,
        "iov limit preserves EINVAL");
    errno = 0;
    require(process_vm_readv(getpid(), &l, 1, &r, 1, 1) == -1 && errno == EINVAL,
        "invalid flags preserve EINVAL");
    require(process_vm_readv(getpid(), &l, 0, &r, 1, 0) == 0, "empty vector returns zero");
    char normal[] = "ordinary-memory";
    r = {normal, sizeof(normal)};
    require(process_vm_readv(getpid(), &l, 1, &r, 1, 0) == sizeof(normal)
        && !memcmp(bytes, normal, sizeof(normal)), "ordinary memory is unchanged");
    uint32_t changed[4];
    memcpy(changed, installed, 16);
    changed[3] = 0xd503203fu; // 第三方后来改过的指令。
    patch(changed);
    r = {entry, 16};
    require(process_vm_readv(getpid(), &l, 1, &r, 1, 0) == 16 && !memcmp(bytes, changed, 16),
        "later third party modification remains visible");
    patch(installed);
    int pipes[2];
    require(pipe(pipes) == 0, "child synchronization pipe");
    pid_t child = fork();
    require(child >= 0, "fork retains libc stack dispatch");
    if (!child) {
        close(pipes[1]);
        char token;
        read(pipes[0], &token, 1);
        _exit(0);
    }
    close(pipes[0]);
    require(process_vm_readv(child, &l, 1, &r, 1, 0) == 16 && !memcmp(bytes, installed, 16),
        "another process code is unchanged");
    require(write(pipes[1], "x", 1) == 1, "release child");
    close(pipes[1]);
    int status;
    require(waitpid(child, &status, 0) == child && status == 0, "child exits normally");
    puts("ALL PASS production nativecompat ARM64 fixture");
}
