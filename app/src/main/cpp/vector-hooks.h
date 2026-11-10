#pragma once
#include <android/log.h>
#include <jni.h>
#include <link.h>
#include <dlfcn.h>
#include <sys/stat.h>
#include <sys/mman.h>
#include <unistd.h>
#include <climits>
#include <cstdio>
#include <cstdint>
#include <cinttypes>
#include <cstring>
#include <algorithm>
#include <atomic>
#include <unordered_set>
#include <vector>
using Hook = int (*)(void *, void *, void **);
using OnLoad = void (*)(const char *, void *);
struct NativeAPIEntries { uint32_t version; Hook hookFunc; int (*unhookFunc)(void *); };
namespace {
std::atomic<int> hookCount{0};
std::unordered_set<void *> hookedSymbols;
// Local copy of the verified ScreenshotShield compatibility fix. This project builds independently.
// Only anonymize Vector's entire shared RO linker file view; keep addresses and executable mappings.
void anonymizeLinkerFileViews() {
    struct View { uintptr_t start; size_t size; };
    std::vector<View> views;
    FILE *maps = fopen("/proc/self/maps", "r");
    if (!maps) return;
    char line[PATH_MAX + 256];
    const long page = sysconf(_SC_PAGESIZE);
    while (page > 0 && fgets(line, sizeof(line), maps)) {
        uintptr_t start = 0, end = 0;
        unsigned long offset = 0;
        char permissions[5]{}, path[PATH_MAX]{};
        if (sscanf(line, "%" SCNxPTR "-%" SCNxPTR " %4s %lx %*s %*s %4095s",
            &start, &end, permissions, &offset, path) != 5) continue;
        if (strcmp(permissions, "r--s") || offset || end <= start) continue;
#ifdef __LP64__
        const char *apex = "/apex/com.android.runtime/bin/linker64";
        const char *system = "/system/bin/linker64";
#else
        const char *apex = "/apex/com.android.runtime/bin/linker";
        const char *system = "/system/bin/linker";
#endif
        if (strcmp(path, apex) && strcmp(path, system)) continue;
        struct stat metadata{};
        if (stat(path, &metadata) || metadata.st_size <= 0) continue;
        size_t size = static_cast<size_t>(metadata.st_size);
        size_t rounded = (size + page - 1) / page * page;
        if (end - start != rounded || size < sizeof(ElfW(Ehdr))) continue;
        auto *header = reinterpret_cast<const ElfW(Ehdr) *>(start);
        if (memcmp(header->e_ident, ELFMAG, SELFMAG) || header->e_type != ET_DYN
            || header->e_phentsize != sizeof(ElfW(Phdr)) || header->e_phoff > size
            || header->e_phnum > (size - header->e_phoff) / sizeof(ElfW(Phdr))) continue;
        auto *programs = reinterpret_cast<const ElfW(Phdr) *>(start + header->e_phoff);
        bool executable = false;
        for (size_t i = 0; i < header->e_phnum; ++i)
            executable |= programs[i].p_type == PT_LOAD && (programs[i].p_flags & PF_X);
        if (executable) views.push_back({start, rounded});
    }
    fclose(maps);
    for (const auto &view : views) {
        void *copy = mmap(nullptr, view.size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        if (copy == MAP_FAILED) continue;
        memcpy(copy, reinterpret_cast<const void *>(view.start), view.size);
        if (mprotect(copy, view.size, PROT_READ) != 0
            || mremap(copy, view.size, view.size, MREMAP_MAYMOVE | MREMAP_FIXED,
                reinterpret_cast<void *>(view.start)) == MAP_FAILED) munmap(copy, view.size);
    }
}
size_t symbolSize(void *address, const char *name) {
    Dl_info info{};
    if (!dladdr(address, &info) || !info.dli_fbase) return 0;
    auto base = reinterpret_cast<uintptr_t>(info.dli_fbase);
    auto *header = reinterpret_cast<const ElfW(Ehdr) *>(base);
    auto *programs = reinterpret_cast<const ElfW(Phdr) *>(base + header->e_phoff);
    const ElfW(Dyn) *dynamic = nullptr;
    for (size_t i = 0; i < header->e_phnum; ++i)
        if (programs[i].p_type == PT_DYNAMIC)
            dynamic = reinterpret_cast<const ElfW(Dyn) *>(base + programs[i].p_vaddr);
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
    for (size_t i = 0; i < count; ++i)
        if (symbols[i].st_name < stringSize && !strcmp(strings + symbols[i].st_name, name))
            return symbols[i].st_size;
    return 0;
}
template <class R, class O>
bool install(const NativeAPIEntries *api, const char *name, R replacement, O *original) {
    // Vector's loader mutex is held here. Do not call dlopen.
    void *symbol = dlsym(RTLD_DEFAULT, name);
    if (!symbol || symbolSize(symbol, name) < 16 || !hookedSymbols.insert(symbol).second) return false;
    if (api->hookFunc(symbol, reinterpret_cast<void *>(replacement),
        reinterpret_cast<void **>(original)) != 0) return false;
    ++hookCount;
    return true;
}
}
