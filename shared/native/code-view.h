#pragma once
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <mutex>
#include <vector>

namespace shield_code {
struct Entry { uintptr_t address; std::vector<uint8_t> original, installed; };
class Views {
    std::mutex lock_;
    std::vector<Entry> entries_;
public:
    bool owns(const void *address) {
        std::lock_guard<std::mutex> guard(lock_);
        for (const auto &entry : entries_)
            if (entry.address == reinterpret_cast<uintptr_t>(address)
                && !memcmp(address, entry.installed.data(), entry.installed.size())) return true;
        return false;
    }
    void remember(uintptr_t at, const void *before, const void *after, size_t n) {
        if (!at || !n || n > 256) return;
        std::lock_guard<std::mutex> guard(lock_);
        entries_.push_back({at, {static_cast<const uint8_t *>(before),static_cast<const uint8_t *>(before)+n},
            {static_cast<const uint8_t *>(after),static_cast<const uint8_t *>(after)+n}});
    }
    void overlay(uintptr_t offset, void *buffer, size_t n) {
        if (!buffer || n > UINTPTR_MAX - offset) return;
        std::lock_guard<std::mutex> guard(lock_);
        for (const auto &e : entries_) {
            uintptr_t begin = std::max(offset,e.address);
            uintptr_t end = std::min(offset+n,e.address+e.original.size());
            if (begin >= end) continue;
            size_t from = begin - e.address, target = begin - offset, size = end - begin;
            // Do not conceal a later third-party modification to this entry.
            if (!memcmp(static_cast<uint8_t *>(buffer)+target,e.installed.data()+from,size))
                memcpy(static_cast<uint8_t *>(buffer)+target,e.original.data()+from,size);
        }
    }
};
}
