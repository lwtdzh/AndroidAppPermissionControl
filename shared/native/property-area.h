#pragma once
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace shield_properties {
// Offset-based codec for Bionic's v0xfc6ed0ab property area. No casts of
// untrusted offsets into native objects; malformed snapshots are rejected.
class Area {
    std::vector<uint8_t> bytes_;
    std::vector<uint8_t> original_;
    uint32_t used_ = 0;
    std::unordered_set<uint32_t> visited_;
    std::vector<std::vector<std::pair<size_t,size_t>>> groups_;
    bool range(size_t at, size_t n) const {
        return at <= bytes_.size() && n <= bytes_.size() - at;
    }
    uint32_t word(size_t at) const {
        uint32_t out = 0; memcpy(&out, bytes_.data() + at, 4); return out;
    }
    void word(size_t at, uint32_t v) { memcpy(bytes_.data() + at, &v, 4); }
    bool text(size_t at, size_t end, std::string &out) const {
        if (at >= end || !range(at, end - at)) return false;
        auto *zero = static_cast<const uint8_t *>(memchr(bytes_.data() + at, 0, end - at));
        if (!zero) return false;
        out.assign(reinterpret_cast<const char *>(bytes_.data() + at), zero - bytes_.data() - at);
        return true;
    }
    bool node(uint32_t offset, bool root = false, size_t depth = 0) {
        if (depth > 512) return false;
        if (offset % 4 || offset > used_ || used_ - offset < 20 ||
            !visited_.insert(offset).second || visited_.size() > 65536) return false;
        size_t at = header + offset;
        uint32_t n = word(at);
        std::string token;
        if (!root && (n > 4096 || !text(at + 20, header + used_, token) || token.size() != n))
            return false;
        uint32_t prop = word(at + 4);
        if (prop) {
            if (prop % 4 || prop > used_ || used_ - prop < 97) return false;
            size_t p = header + prop;
            std::string name, value;
            uint32_t serial = word(p);
            if (serial & 1 || !text(p + 96, header + used_, name) || name.empty() ||
                !names_.insert(name).second) return false;
            bool isLong = serial & (1u << 16);
            size_t start = p + 4;
            if (isLong) {
                if (name.compare(0, 3, "ro.")) return false;
                uint32_t relative = word(p + 60);
                if (relative < 96 + name.size() + 1 || relative > header + used_ - p) return false;
                start = p + relative;
            }
            if (!text(start, isLong ? header + used_ : p + 96, value) ||
                (!isLong && value.size() != serial >> 24)) return false;
            properties.push_back({name, p, start, value.size() + 1});
        }
        for (size_t field : {size_t(8), size_t(12), size_t(16)}) {
            uint32_t child = word(at + field);
            if (child && !node(child,false,depth+1)) return false;
        }
        return true;
    }
    std::unordered_set<std::string> names_;
public:
    static constexpr size_t header = 128;
    struct Property { std::string name; size_t info, value, valueSize; };
    std::vector<Property> properties;
    std::vector<std::pair<size_t,size_t>> changed;
    bool load(const void *source, size_t size) {
        bytes_.clear(); original_.clear(); groups_.clear();
        properties.clear(); changed.clear(); names_.clear(); visited_.clear();
        if (!source || size < header + 112 || size > 16 * 1024 * 1024) return false;
        bytes_.assign(static_cast<const uint8_t *>(source), static_cast<const uint8_t *>(source) + size);
        used_ = word(0);
        bool valid=used_ >= 112 && used_ <= size - header &&
            word(8) == 0x504f5250 && word(12) == 0xfc6ed0ab && node(0, true);
        if(valid)original_=bytes_;
        return valid;
    }
    bool replace(const std::unordered_map<std::string,std::string> &values, bool inPlace = false) {
        auto saved = bytes_; uint32_t previousUsed = used_;
        for (const auto &p : properties) {
            auto it = values.find(p.name);
            if (it == values.end() || p.name.compare(0, 3, "ro.")) continue;
            const auto &v = it->second;
            size_t begin=changed.size();
            if (v.find('\0') != std::string::npos || v.size() > 1024 * 1024) {
                bytes_ = std::move(saved); used_ = previousUsed; changed.clear(); return false;
            }
            size_t next = p.info + 4;
            if (v.size() >= 92) {
                if(inPlace) {
                    if(p.value == p.info+4 || v.size()+1 > p.valueSize) continue;
                    next=p.value;
                } else {
                size_t allocated = (v.size() + 4) & ~size_t(3);
                if (allocated > bytes_.size() - header - used_) {
                    bytes_ = std::move(saved); used_ = previousUsed; changed.clear(); return false;
                }
                next = header + used_; used_ += allocated;
                }
            }
            // Erase both the legacy union and the previous long payload, even
            // when the new value is shorter. No real-value suffix is retained.
            memset(bytes_.data() + p.info + 4, 0, 92);
            memset(bytes_.data() + p.value, 0, p.valueSize);
            changed.emplace_back(p.info, 96);
            changed.emplace_back(p.value, p.valueSize);
            if (v.size() >= 92) {
                constexpr char compatibility[] = "Must use __system_property_read_callback() to read";
                memcpy(bytes_.data() + p.info + 4, compatibility, sizeof(compatibility));
                word(p.info + 60, static_cast<uint32_t>(next - p.info));
                word(p.info, (50u << 24) | (1u << 16));
                changed.emplace_back(next, v.size() + 1);
            } else word(p.info, static_cast<uint32_t>(v.size()) << 24);
            memcpy(bytes_.data() + next, v.c_str(), v.size() + 1);
            groups_.emplace_back(changed.begin()+begin,changed.end());
        }
        if (used_!=previousUsed) { word(0, used_); changed.emplace_back(0, 4); }
        return true;
    }
    const std::vector<uint8_t> &bytes() const { return bytes_; }
    // COW remapping is page-granular. A page containing a mutable property
    // must retain its shared backing and futex updates from Android init.
    std::vector<size_t> immutablePages(size_t page) {
        if(!page)return {};
        std::unordered_set<size_t> needed, mutablePages;
        auto pages = [page](size_t at, size_t n, std::unordered_set<size_t> &out) {
            for (size_t p = at / page; p <= (at + n - 1) / page; ++p) out.insert(p * page);
        };
        for (const auto &p : properties) if (p.name.compare(0, 3, "ro.")) {
            pages(p.info, 96 + p.name.size() + 1, mutablePages);
            pages(p.value, p.valueSize, mutablePages);
        }
        // Global serial and dirty backup are shared state, even if all leaf
        // properties currently happen to be immutable.
        mutablePages.insert(0);
        for(const auto &group:groups_) {
            std::unordered_set<size_t> groupPages;
            for(auto [at,n]:group)if(n)pages(at,n,groupPages);
            bool safe=true;
            for(size_t p:groupPages)if(mutablePages.count(p))safe=false;
            if(safe)needed.insert(groupPages.begin(),groupPages.end());
            else for(auto [at,n]:group)memcpy(bytes_.data()+at,original_.data()+at,n);
        }
        std::vector<size_t> out;
        for (size_t p : needed) if (!mutablePages.count(p)) out.push_back(p);
        std::sort(out.begin(),out.end()); return out;
    }
};
}
