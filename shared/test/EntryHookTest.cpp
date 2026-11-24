#include "../native/entry-hook.h"
#include <pthread.h>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cerrno>
#include <sys/syscall.h>
#include <sys/ioctl.h>
#include <sched.h>
#include <linux/memfd.h>
#include <fcntl.h>
#include <dlfcn.h>
#include <link.h>
#if defined(__aarch64__)
extern "C" long sealedFixture(long, void *, size_t);
asm(".text\n.align 4\n.global sealedFixture\n.type sealedFixture,%function\n"
    "sealedFixture:\nmov x0,#42\nret\nnop\nnop\n");
#endif

using Fn = long (*)(long, void *, size_t);
Fn firstOriginal, secondOriginal;
std::atomic<int> firstCalls{0}, secondCalls{0};
long first(long a, void *b, size_t c) { ++firstCalls; return firstOriginal(a, b, c); }
long second(long a, void *b, size_t c) { ++secondCalls; return secondOriginal(a, b, c); }
void require(bool ok, const char *name) {
    if (!ok) { std::fprintf(stderr, "FAIL %s errno=%d\n", name, errno); std::exit(1); }
    std::printf("PASS %s\n", name);
}
void *codePage(const uint32_t *words, size_t size) {
    void *page = mmap(nullptr, 4096, PROT_READ | PROT_WRITE, MAP_ANONYMOUS | MAP_PRIVATE, -1, 0);
    require(page != MAP_FAILED, "fixture allocation");
    memcpy(page, words, size);
    __builtin___clear_cache(static_cast<char *>(page), static_cast<char *>(page) + size);
    require(!mprotect(page, 4096, PROT_READ | PROT_EXEC), "fixture executable");
    return page;
}
void numeric(const char *name, const uint32_t *words, size_t bytes, long input, long expected) {
    Fn entry = reinterpret_cast<Fn>(codePage(words, bytes)), backup = nullptr;
    require(entry(input, nullptr, 0) == expected, name);
    shield_entry::Detour patch;
    require(!shield_entry::install(reinterpret_cast<void *>(entry), reinterpret_cast<void *>(first),
        reinterpret_cast<void **>(&backup), &patch), "fixture install");
    firstOriginal = backup; // No concurrent calls to this numeric fixture.
    require(entry(input, nullptr, 0) == expected, name);
    require(shield_entry::restore(patch), "fixture restore");
    require(entry(input, nullptr, 0) == expected, name);
}
std::atomic<bool> started{false};
std::atomic<int> readerTid{0};
int readPipe[2];
Fn blockedEntry;
void *reader(void *) {
    char byte = 0;
    readerTid = static_cast<int>(syscall(SYS_gettid));
    started = true;
    long n = blockedEntry(readPipe[0], &byte, 1);
    require(n == 1 && byte == 'a', "active syscall return survives patch");
    return nullptr;
}
int main() {
    setvbuf(stdout, nullptr, _IONBF, 0);
#if !defined(__aarch64__)
    return 77;
#else
    uint32_t cbz[] = {0xb4000080, 0x91000400, 0xd65f03c0, 0xd503201f, 0xd2800540, 0xd65f03c0};
    numeric("CBZ taken", cbz, sizeof(cbz), 0, 42);
    numeric("CBZ not taken", cbz, sizeof(cbz), 5, 6);
    uint32_t cond[] = {0xf100001f, 0x54000060, 0x91000400, 0xd65f03c0, 0xd2800540, 0xd65f03c0};
    numeric("conditional taken", cond, sizeof(cond), 0, 42);
    numeric("conditional not taken", cond, sizeof(cond), 7, 8);
    uint32_t tbz[] = {0x36000080, 0x91000400, 0xd65f03c0, 0xd503201f, 0xd2800540, 0xd65f03c0};
    numeric("TBZ taken", tbz, sizeof(tbz), 2, 42);
    numeric("TBZ not taken", tbz, sizeof(tbz), 3, 4);
    uint32_t internal[] = {0x14000002, 0xd2800c60, 0x91000400, 0xd65f03c0};
    numeric("branch inside displaced prefix", internal, sizeof(internal), 10, 11);
    uint32_t literal[] = {0x58000080, 0xd65f03c0, 0xd503201f, 0xd503201f, 42, 0};
    numeric("external LDR literal", literal, sizeof(literal), 0, 42);
    uint32_t adr[] = {0x10000081, 0xf9400020, 0xd65f03c0, 0xd503201f, 57, 0};
    numeric("ADR address", adr, sizeof(adr), 0, 57);
    uint32_t result[] = {0xd2800540, 0xd65f03c0, 0xd503201f, 0xd503201f};
    int sealed = open("/proc/self/exe", O_RDONLY | O_CLOEXEC);
    Dl_info info{};
    require(sealed >= 0 && dladdr(reinterpret_cast<void *>(sealedFixture), &info), "read-only executable fixture");
    auto *header = static_cast<ElfW(Ehdr) *>(info.dli_fbase);
    auto *programs = reinterpret_cast<ElfW(Phdr) *>(reinterpret_cast<char *>(header) + header->e_phoff);
    uintptr_t virtualAddress = reinterpret_cast<uintptr_t>(sealedFixture) - reinterpret_cast<uintptr_t>(header);
    uintptr_t offset = 0;
    for (unsigned i = 0; i < header->e_phnum; ++i)
        if (programs[i].p_type == PT_LOAD && virtualAddress >= programs[i].p_vaddr
            && virtualAddress < programs[i].p_vaddr + programs[i].p_filesz)
            offset = programs[i].p_offset + virtualAddress - programs[i].p_vaddr;
    require(offset != 0, "read-only function file offset");
    void *sharedPage = mmap(nullptr, 4096, PROT_READ | PROT_EXEC, MAP_SHARED, sealed, offset & ~uintptr_t(4095));
    void *shared = static_cast<char *>(sharedPage) + (offset & 4095);
    require(sharedPage != MAP_FAILED && mprotect(sharedPage, 4096, PROT_READ | PROT_WRITE | PROT_EXEC) < 0,
        "shared read-only page rejects mprotect");
    shield_entry::Detour sealedPatch;
    require(!shield_entry::install(shared, reinterpret_cast<void *>(first),
        reinterpret_cast<void **>(&firstOriginal), &sealedPatch), "sealed page detour");
    require(reinterpret_cast<Fn>(shared)(0, nullptr, 0) == 42, "sealed page hook behavior");
    require(!memcmp(static_cast<char *>(shared) + 4, reinterpret_cast<char *>(result) + 4,
        sizeof(result) - 4), "sealed page remaining bytes preserved");
    require(shield_entry::restore(sealedPatch)
        && !memcmp(shared, result, sizeof(result)), "sealed page restored bytes");
    close(sealed);
    void *resultFn = codePage(result, sizeof(result));
    uint32_t redirect[] = {0x58000050, 0xd61f0200, 0, 0};
    memcpy(redirect + 2, &resultFn, sizeof(resultFn));
    Fn entry = reinterpret_cast<Fn>(codePage(redirect, sizeof(redirect)));
    require(!shield_entry::install(reinterpret_cast<void *>(entry), reinterpret_cast<void *>(first),
        reinterpret_cast<void **>(&firstOriginal)), "literal detour install");
    require(entry(0, nullptr, 0) == 42, "existing literal owner preserved");
    // Simulate a second hooker's 16-byte entry patch after saving its backup.
    require(!shield_entry::install(reinterpret_cast<void *>(entry), reinterpret_cast<void *>(second),
        reinterpret_cast<void **>(&secondOriginal)), "second hook backup");
    void *secondFn = reinterpret_cast<void *>(second);
    memcpy(redirect + 2, &secondFn, sizeof(secondFn));
    require(!mprotect(reinterpret_cast<void *>(entry), 4096, PROT_READ | PROT_WRITE | PROT_EXEC), "second patch writable");
    memcpy(reinterpret_cast<void *>(entry), redirect, sizeof(redirect));
    __builtin___clear_cache(reinterpret_cast<char *>(entry), reinterpret_cast<char *>(entry) + 16);
    require(!mprotect(reinterpret_cast<void *>(entry), 4096, PROT_READ | PROT_EXEC), "second patch executable");
    require(entry(0, nullptr, 0) == 42, "two hooks and changed embedded literal");
    uint32_t sysread[] = {0xd28007e8, 0xd4000001, 0xd65f03c0, 0xd503201f}; // SYS_read=63
    blockedEntry = reinterpret_cast<Fn>(codePage(sysread, sizeof(sysread)));
    require(!pipe(readPipe), "pipe fixture");
    pthread_t thread;
    require(!pthread_create(&thread, nullptr, reader, nullptr), "start blocking read");
    while (!started.load()) sched_yield();
    // Prove the kernel is waiting in read before modifying the return path.
    bool sleeping = false;
    for (int attempt = 0; attempt < 10000 && !sleeping; ++attempt) {
        char path[128];
        snprintf(path, sizeof(path), "/proc/self/task/%d/syscall", readerTid.load());
        FILE *state = fopen(path, "r");
        long number = -1;
        unsigned long fd = 0;
        if (state) {
            sleeping = fscanf(state, "%ld %lx", &number, &fd) == 2
                && number == SYS_read && fd == static_cast<unsigned long>(readPipe[0]);
            fclose(state);
        }
        if (!sleeping) sched_yield();
    }
    require(sleeping, "kernel confirms blocked read before patch");
    uint32_t returnWords[2];
    memcpy(returnWords, reinterpret_cast<char *>(blockedEntry) + 8, sizeof(returnWords));
    require(!shield_entry::install(reinterpret_cast<void *>(blockedEntry), reinterpret_cast<void *>(first),
        reinterpret_cast<void **>(&firstOriginal)), "active read install");
    require(!memcmp(returnWords, reinterpret_cast<char *>(blockedEntry) + 8, sizeof(returnWords)), "syscall return bytes unchanged");
    require(write(readPipe[1], "a", 1) == 1, "unblock old read");
    require(!pthread_join(thread, nullptr), "old read completed");
    require(write(readPipe[1], "b", 1) == 1, "new read data");
    char byte = 0;
    int calls = firstCalls.load();
    require(blockedEntry(readPipe[0], &byte, 1) == 1 && byte == 'b'
        && firstCalls.load() == calls + 1, "new read uses full backup and hook");
    close(readPipe[0]); close(readPipe[1]);
    std::printf("ALL PASS ARM64 entry fixtures\n");
    return 0;
#endif
}
