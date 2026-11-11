#pragma once
#include <link.h>
#include <cstring>
#include <cstdint>
#include <algorithm>

// Android's app namespace cannot dlopen private system libraries even when
// zygote already loaded them. Resolve a defined symbol from that live ELF only.
inline void *loadedSymbol(const char *library, const char *name) {
    struct Search { const char *library; const char *name; void *address; } search{library, name, nullptr};
    dl_iterate_phdr([](dl_phdr_info *info, size_t, void *cookie) {
        auto &query = *static_cast<Search *>(cookie);
        const char *path = info->dlpi_name ? info->dlpi_name : "";
        const char *file = strrchr(path, '/');
        if (strcmp(file ? file + 1 : path, query.library)) return 0;
        uintptr_t base = info->dlpi_addr;
        const ElfW(Dyn) *dynamic = nullptr;
        for (size_t i = 0; i < info->dlpi_phnum; ++i)
            if (info->dlpi_phdr[i].p_type == PT_DYNAMIC)
                dynamic = reinterpret_cast<const ElfW(Dyn) *>(base + info->dlpi_phdr[i].p_vaddr);
        if (!dynamic) return 0;
        const ElfW(Sym) *symbols = nullptr;
        const char *strings = nullptr;
        const uint32_t *gnu = nullptr;
        size_t count = 0, stringsSize = 0;
        auto pointer = [base](ElfW(Addr) value) { return value >= base ? value : base + value; };
        for (auto *entry = dynamic; entry->d_tag != DT_NULL; ++entry) {
            switch (entry->d_tag) {
                case DT_SYMTAB: symbols = reinterpret_cast<const ElfW(Sym) *>(pointer(entry->d_un.d_ptr)); break;
                case DT_STRTAB: strings = reinterpret_cast<const char *>(pointer(entry->d_un.d_ptr)); break;
                case DT_STRSZ: stringsSize = entry->d_un.d_val; break;
                case DT_HASH: count = reinterpret_cast<const uint32_t *>(pointer(entry->d_un.d_ptr))[1]; break;
                case DT_GNU_HASH: gnu = reinterpret_cast<const uint32_t *>(pointer(entry->d_un.d_ptr)); break;
                default: break;
            }
        }
        if (!symbols || !strings) return 0;
        if (!count && gnu) {
            uint32_t offset = gnu[1];
            auto *buckets = reinterpret_cast<const uint32_t *>(
                reinterpret_cast<const ElfW(Addr) *>(gnu + 4) + gnu[2]);
            uint32_t last = 0;
            for (uint32_t i = 0; i < gnu[0]; ++i) last = std::max(last, buckets[i]);
            auto *chains = buckets + gnu[0];
            count = offset;
            if (last >= offset) {
                count = last;
                while (count < 1000000 && !(chains[count++ - offset] & 1)) {}
            }
        }
        if (count > 1000000) return 0;
        for (size_t i = 0; i < count; ++i)
            if (symbols[i].st_shndx != SHN_UNDEF && symbols[i].st_name < stringsSize
                && !strcmp(strings + symbols[i].st_name, query.name)) {
                query.address = reinterpret_cast<void *>(base + symbols[i].st_value);
                return 1;
            }
        return 0;
    }, &search);
    return search.address;
}
