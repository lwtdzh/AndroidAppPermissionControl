#pragma once
#include <elf.h>
#include <link.h>
#include "code-view.h"

namespace shield_code {
// 从磁盘 ELF 取指令，按实际加载地址定位；只接受跳向已确认框架的入口。
inline uintptr_t arm64Redirect(uintptr_t pc, const uint32_t *w) {
    auto signedValue = [](uint32_t value, unsigned bits) {
        return static_cast<int64_t>(value ^ (1u << (bits - 1))) - (1ll << (bits - 1));
    };
    if ((w[0] & 0xfc000000u) == 0x14000000u)
        return pc + signedValue(w[0] & 0x03ffffffu, 26) * 4;
    if ((w[0] & 0xffffffe0u) == 0x58000040u
        && (w[1] & 0xfffffc1fu) == 0xd61f0000u
        && (w[0] & 31u) == ((w[1] >> 5) & 31u)) {
        uintptr_t target = 0;
        memcpy(&target, w + 2, sizeof(target));
        return target;
    }
    unsigned reg = w[0] & 31u;
    if ((w[0] & 0x9f000000u) == 0x90000000u
        && (w[1] & 0xffc00000u) == 0x91000000u
        && (w[1] & 31u) == reg && ((w[1] >> 5) & 31u) == reg
        && w[2] == (0xd61f0000u | (reg << 5))) {
        int64_t pages = signedValue(((w[0] >> 5) & 0x7ffffu) << 2 | ((w[0] >> 29) & 3), 21);
        return (pc & ~uintptr_t(4095)) + pages * 4096 + ((w[1] >> 10) & 4095u);
    }
    return 0;
}

template<class Owns>
size_t captureElf(const void *file, size_t size, uintptr_t bias,
                  const ElfW(Phdr) *loaded, size_t loadedCount, Owns owns, Views &views) {
    auto fits = [size](uint64_t offset, uint64_t n) {
        return offset <= size && n <= size - offset;
    };
    if (!file || size < sizeof(ElfW(Ehdr))) return 0;
    const auto *bytes = static_cast<const uint8_t *>(file);
    ElfW(Ehdr) header;
    memcpy(&header, bytes, sizeof(header));
    if (memcmp(header.e_ident, ELFMAG, SELFMAG) || header.e_type != ET_DYN
        || header.e_ident[EI_DATA] != ELFDATA2LSB
        || header.e_ident[EI_CLASS] != (sizeof(void *) == 8 ? ELFCLASS64 : ELFCLASS32)
        || header.e_machine != EM_AARCH64 || header.e_shentsize != sizeof(ElfW(Shdr))
        || header.e_phentsize != sizeof(ElfW(Phdr))
        || !fits(header.e_shoff, uint64_t(header.e_shnum) * sizeof(ElfW(Shdr)))
        || !fits(header.e_phoff, uint64_t(header.e_phnum) * sizeof(ElfW(Phdr)))) return 0;
    auto section = [&](size_t i) {
        ElfW(Shdr) out;
        memcpy(&out, bytes + header.e_shoff + i * sizeof(out), sizeof(out));
        return out;
    };
    size_t count = 0;
    for (size_t i = 0; i < header.e_shnum; ++i) {
        auto table = section(i);
        if ((table.sh_type != SHT_SYMTAB && table.sh_type != SHT_DYNSYM)
            || table.sh_entsize != sizeof(ElfW(Sym)) || table.sh_link >= header.e_shnum
            || !fits(table.sh_offset, table.sh_size)) continue;
        auto strings = section(table.sh_link);
        if (strings.sh_type != SHT_STRTAB || !fits(strings.sh_offset, strings.sh_size)) continue;
        for (size_t j = 0; j < table.sh_size / sizeof(ElfW(Sym)); ++j) {
            ElfW(Sym) symbol;
            memcpy(&symbol, bytes + table.sh_offset + j * sizeof(symbol), sizeof(symbol));
            if (ELF64_ST_TYPE(symbol.st_info) != STT_FUNC || symbol.st_shndx == SHN_UNDEF
                || symbol.st_shndx >= header.e_shnum || symbol.st_size < 16
                || symbol.st_name >= strings.sh_size || (symbol.st_value & 3)
                || symbol.st_value > UINTPTR_MAX - bias) continue;
            uintptr_t address = bias + symbol.st_value;
            bool executable = false;
            for (size_t k = 0; k < loadedCount; ++k) {
                const auto &p = loaded[k];
                if (p.p_type == PT_LOAD && (p.p_flags & (PF_X | PF_R)) == (PF_X | PF_R)
                    && symbol.st_value >= p.p_vaddr && p.p_memsz >= 16
                    && symbol.st_value - p.p_vaddr <= p.p_memsz - 16) executable = true;
            }
            if (!executable) continue;
            uint64_t offset = UINT64_MAX;
            for (size_t k = 0; k < header.e_phnum; ++k) {
                ElfW(Phdr) p;
                memcpy(&p, bytes + header.e_phoff + k * sizeof(p), sizeof(p));
                if (p.p_type == PT_LOAD && (p.p_flags & PF_X)
                    && p.p_filesz >= 16 && symbol.st_value >= p.p_vaddr
                    && symbol.st_value - p.p_vaddr <= p.p_filesz - 16
                    && fits(p.p_offset, p.p_filesz)) {
                    offset = p.p_offset + symbol.st_value - p.p_vaddr;
                    break;
                }
            }
            if (!fits(offset, 16)) continue;
            uint32_t current[4];
            memcpy(current, reinterpret_cast<const void *>(address), sizeof(current));
            uintptr_t target = arm64Redirect(address, current);
            if (!target || !owns(target) || !memcmp(current, bytes + offset, 16)) continue;
            views.remember(address, bytes + offset, current, 16);
            ++count;
        }
    }
    return count;
}
}
