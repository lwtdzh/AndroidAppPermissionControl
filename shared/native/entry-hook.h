#pragma once
#include <sys/mman.h>
#include <unistd.h>
#include <cstdint>
#include <cerrno>
#include <cstring>
#include <initializer_list>

// ARM64 entry detours: publish only one instruction, but relocate the complete
// 16-byte prefix. A later owner may replace all 16 bytes of the original entry.
namespace shield_entry {
inline int64_t signedBits(uint32_t value, unsigned bits) {
    return static_cast<int64_t>(value ^ (1u << (bits - 1))) - (1ll << (bits - 1));
}
inline bool branchWord(uintptr_t from, uintptr_t to, uint32_t *word, bool link = false) {
    int64_t delta = static_cast<int64_t>(to) - static_cast<int64_t>(from);
    if ((delta & 3) || delta < -(1ll << 27) || delta >= (1ll << 27)) return false;
    *word = (link ? 0x94000000u : 0x14000000u) | (static_cast<uint32_t>(delta / 4) & 0x03ffffffu);
    return true;
}
inline void addressWords(uint32_t *out, unsigned reg, uintptr_t address) {
    for (unsigned i = 0; i < 4; ++i)
        out[i] = (i ? 0xf2800000u : 0xd2800000u) | (i << 21)
            | (static_cast<uint32_t>((address >> (16 * i)) & 0xffff) << 5) | reg;
}
struct Detour {
    void *entry = nullptr;
    void *page = nullptr;
    size_t pageSize = 0;
    uint32_t before = 0, installed = 0;
};
struct Attempt { int distant = 0, relocation = 0, protection = 0; uintptr_t last = 0; };
inline bool writableCode(uintptr_t start, size_t size) {
    if (!mprotect(reinterpret_cast<void *>(start), size, PROT_READ | PROT_WRITE | PROT_EXEC)) return true;
    if (errno != EACCES && errno != EPERM) return false;
    // Vector can map its sealed, read-only memfd as shared executable pages.
    // Preserve the complete live page at the same address in a private mapping.
    void *copy = mmap(nullptr, size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (copy == MAP_FAILED) return false;
    memcpy(copy, reinterpret_cast<void *>(start), size);
    __builtin___clear_cache(static_cast<char *>(copy), static_cast<char *>(copy) + size);
    if (mprotect(copy, size, PROT_READ | PROT_WRITE | PROT_EXEC)
        || mremap(copy, size, size, MREMAP_MAYMOVE | MREMAP_FIXED,
            reinterpret_cast<void *>(start)) == MAP_FAILED) {
        munmap(copy, size);
        return false;
    }
    return true;
}
// Called only before publishing the detour. Slots have fixed addresses so a
// branch into the displaced prefix targets the corresponding relocated slot.
inline bool relocate(const uint32_t *saved, uintptr_t entry, uint32_t *out, uintptr_t output,
                     uintptr_t literals) {
    constexpr size_t stride = 16; // 64 bytes per original instruction.
    bool needed[4]{true, false, false, false}, done[4]{};
    auto target = [entry, output, &needed](uintptr_t at) {
        if (at >= entry && at < entry + 16 && !((at - entry) & 3)) {
            needed[(at - entry) / 4] = true;
            return output + (at - entry) / 4 * 64;
        }
        return at;
    };
    for (unsigned pass = 0; pass < 4; ++pass) for (unsigned i = 0; i < 4; ++i) {
        if (!needed[i] || done[i]) continue;
        done[i] = true;
        bool terminal = false;
        uint32_t w = saved[i], *slot = out + i * stride;
        uintptr_t pc = entry + i * 4, at = output + i * 64;
        size_t used = 1;
        slot[0] = w;
        if ((w & 0x7c000000u) == 0x14000000u) { // B / BL
            uintptr_t to = target(pc + signedBits(w & 0x03ffffffu, 26) * 4);
            bool link = w & 0x80000000u;
            if (!branchWord(at, to, slot, link)) return false;
            terminal = !link;
        } else if ((w & 0xff000010u) == 0x54000000u
                   || (w & 0x7e000000u) == 0x34000000u
                   || (w & 0x7e000000u) == 0x36000000u) {
            bool bitTest = (w & 0x7e000000u) == 0x36000000u;
            unsigned bits = bitTest ? 14 : 19;
            uint32_t mask = ((1u << bits) - 1) << 5;
            uintptr_t to = target(pc + signedBits((w & mask) >> 5, bits) * 4);
            // Invert the condition and skip the unrestricted direct branch.
            slot[0] = ((w ^ ((w & 0xff000010u) == 0x54000000u ? 1u : 0x01000000u))
                       & ~mask) | (2u << 5);
            if (!branchWord(at + 4, to, slot + 1)) return false;
            used = 2;
        } else if ((w & 0x1f000000u) == 0x10000000u) { // ADR / ADRP
            int64_t imm = signedBits(((w >> 5) & 0x7ffffu) << 2 | ((w >> 29) & 3), 21);
            uintptr_t value = w & 0x80000000u ? (pc & ~uintptr_t(4095)) + imm * 4096 : pc + imm;
            addressWords(slot, w & 31, value);
            used = 4;
        } else if ((w & 0x3b000000u) == 0x18000000u) { // LDR literal / PRFM
            uintptr_t value = pc + signedBits((w >> 5) & 0x7ffffu, 19) * 4;
            // Embedded detour literals must not be fetched from the mutable entry.
            if (value >= entry && value < entry + 16) {
                unsigned bytes = (w & 0x04000000u) ? (4u << (w >> 30)) : ((w >> 30) == 1 ? 8 : 4);
                if (bytes > 16 || value + bytes > entry + 16) return false;
                value = literals + value - entry;
            }
            int64_t delta = static_cast<int64_t>(value) - static_cast<int64_t>(at);
            if (!(delta & 3) && delta >= -(1ll << 20) && delta < (1ll << 20)) {
                slot[0] = (w & ~0x00ffffe0u) | ((static_cast<uint32_t>(delta / 4) & 0x7ffffu) << 5);
            } else {
                unsigned reg = w & 31, kind = w >> 30;
                // Integer destination can hold the address until its load.
                if (!(w & 0x04000000u) && kind < 3 && reg != 31) {
                    addressWords(slot, reg, value);
                    slot[4] = (kind == 0 ? 0xb9400000u : kind == 1 ? 0xf9400000u : 0xb9800000u)
                        | (reg << 5) | reg;
                    used = 5;
                } else {
                    // Preserve x16 and stack alignment for SIMD, XZR and PRFM.
                    slot[0] = 0xf81f0ff0u; // STR X16, [SP, #-16]!
                    addressWords(slot + 1, 16, value);
                    uint32_t load;
                    if (w & 0x04000000u) {
                        if (kind == 3) return false;
                        load = kind == 0 ? 0xbd400000u : kind == 1 ? 0xfd400000u : 0x3dc00000u;
                    } else load = kind == 3 ? 0xf9800000u
                        : kind == 0 ? 0xb9400000u : kind == 1 ? 0xf9400000u : 0xb9800000u;
                    slot[5] = load | (16u << 5) | reg;
                    slot[6] = 0xf84107f0u; // LDR X16, [SP], #16
                    used = 7;
                }
            }
        } else if ((w & 0xfffffc1fu) == 0xd61f0000u // BR
                   || (w & 0xfffffc1fu) == 0xd65f0000u) { // RET
            terminal = true;
        }
        if (!terminal) {
            if (i < 3) needed[i + 1] = true;
            if (!branchWord(at + used * 4,
                    i == 3 ? entry + 16 : output + (i + 1) * 64, slot + used)) return false;
        }
    }
    return true;
}
inline int install(void *symbol, void *replacement, void **original, Detour *record = nullptr,
                   Attempt *attempt = nullptr) {
#if defined(__aarch64__)
    if (!symbol || !replacement || !original || (reinterpret_cast<uintptr_t>(symbol) & 3)) return -1;
    const long pageSize = sysconf(_SC_PAGESIZE);
    if (pageSize <= 0) return -1;
    uintptr_t entry = reinterpret_cast<uintptr_t>(symbol);
    uintptr_t start = entry & ~(static_cast<uintptr_t>(pageSize) - 1);
    uint32_t saved[4];
    memcpy(saved, symbol, sizeof(saved));
    for (uintptr_t distance = pageSize; distance < (1u << 27); distance += 1u << 20) {
        for (int direction : {1, -1}) {
            uintptr_t hint = direction > 0 ? start + distance : start - distance;
            void *page = mmap(reinterpret_cast<void *>(hint), pageSize, PROT_READ | PROT_WRITE,
                MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
            if (page == MAP_FAILED) continue;
            uintptr_t address = reinterpret_cast<uintptr_t>(page);
            uint32_t branch = 0;
            if (!branchWord(entry, address, &branch)) {
                if (attempt) { ++attempt->distant; attempt->last = address; }
                munmap(page, pageSize); continue;
            }
            auto *code = static_cast<uint32_t *>(page);
            code[0] = 0x58000050u; // LDR X16, +8
            code[1] = 0xd61f0200u; // BR X16
            memcpy(code + 2, &replacement, sizeof(replacement));
            code[4] = 0xd503245fu; // BTI C at the callable backup.
            memcpy(code + 80, saved, sizeof(saved));
            if (!relocate(saved, entry, code + 8, address + 32, address + 320)
                || !branchWord(address + 20, address + 32, code + 5)) {
                if (attempt) ++attempt->relocation;
                munmap(page, pageSize);
                continue;
            }
            __builtin___clear_cache(static_cast<char *>(page), static_cast<char *>(page) + 336);
            if (mprotect(page, pageSize, PROT_READ | PROT_EXEC)
                || !writableCode(start, pageSize)) {
                if (attempt) attempt->protection = errno;
                munmap(page, pageSize);
                return -1;
            }
            *original = reinterpret_cast<void *>(address + 16);
            __atomic_store_n(static_cast<uint32_t *>(symbol), branch, __ATOMIC_RELEASE);
            __builtin___clear_cache(static_cast<char *>(symbol), static_cast<char *>(symbol) + 4);
            mprotect(reinterpret_cast<void *>(start), pageSize, PROT_READ | PROT_EXEC);
            if (record) *record = {symbol, page, static_cast<size_t>(pageSize), saved[0], branch};
            return 0;
        }
    }
    return -1;
#else
    (void)symbol; (void)replacement; (void)original; (void)record;
    return -1;
#endif
}
inline bool restore(const Detour &detour) {
    if (!detour.entry || __atomic_load_n(static_cast<uint32_t *>(detour.entry), __ATOMIC_ACQUIRE)
        != detour.installed) return false;
    uintptr_t start = reinterpret_cast<uintptr_t>(detour.entry) & ~(detour.pageSize - 1);
    if (!writableCode(start, detour.pageSize)) return false;
    __atomic_store_n(static_cast<uint32_t *>(detour.entry), detour.before, __ATOMIC_RELEASE);
    __builtin___clear_cache(static_cast<char *>(detour.entry), static_cast<char *>(detour.entry) + 4);
    mprotect(reinterpret_cast<void *>(start), detour.pageSize, PROT_READ | PROT_EXEC);
    // Backup pages remain alive: a concurrent caller may still execute one.
    return true;
}
}
