#pragma once

#include <sys/mman.h>
#include <unistd.h>
#include <atomic>
#include <cstdint>
#include <cstring>
#include <limits>
#include <mutex>
#include <new>
#include <string>
#include <unordered_map>
#include <unordered_set>
#ifdef __ANDROID__
#include <fcntl.h>
#include <linux/memfd.h>
#include <sys/syscall.h>
#endif

namespace shield_properties {
// Bionic's stable prop_info wire layout, verified before enabling this adapter.
// We only construct immutable ro.* objects. Published mappings intentionally
// live until process exit: applications may retain pointers without notifying us.
class ReadOnlyViews {
    std::mutex mutex_;
    std::unordered_map<std::string, const void *> objects_;
    std::unordered_set<const void *> owned_;
    std::unordered_map<const void *, std::string> originals_;
public:
    std::atomic<int> failureStage{0};
    static constexpr size_t headerSize = 96, valueOffset = 4, longOffset = 60;
    static constexpr uint32_t longFlag = 1u << 16;
    static constexpr char compatibility[] = "Must use __system_property_read_callback() to read";

    void remember(const void *info, const char *name) {
        if (!info || !name) return;
        std::lock_guard<std::mutex> lock(mutex_);
        if (!owned_.count(info)) originals_.emplace(info, name);
    }
    std::string name(const void *info) {
        std::lock_guard<std::mutex> lock(mutex_);
        auto found = originals_.find(info);
        return found == originals_.end() ? "" : found->second;
    }
    bool owns(const void *info) {
        std::lock_guard<std::mutex> lock(mutex_);
        return owned_.count(info) != 0;
    }
    const void *get(const std::string &name, const std::string &value) {
        if (name.compare(0, 3, "ro.") || name.find('\0') != std::string::npos ||
            value.find('\0') != std::string::npos) return nullptr;
        // Bound both the relative 32-bit offset and the allocation arithmetic.
        if (name.size() > 4096 || value.size() > 1024 * 1024) return nullptr;
        std::string key = name + '\0' + value;
        std::lock_guard<std::mutex> lock(mutex_);
        auto existing = objects_.find(key);
        if (existing != objects_.end()) return existing->second;
        bool isLong = value.size() >= 92;
        size_t offset = headerSize + name.size() + 1;
        size_t required = offset + (isLong ? value.size() + 1 : 0);
        long page = sysconf(_SC_PAGESIZE);
        if (page <= 0 || required > SIZE_MAX - static_cast<size_t>(page)) return nullptr;
        size_t capacity = (required + page - 1) / page * page;
        int fd = -1;
        int flags = MAP_PRIVATE | MAP_ANONYMOUS;
#ifdef __ANDROID__
        // Bionic waits with a shared futex. A read-only anonymous *private*
        // mapping yields EFAULT there and its wait loop never reaches timeout.
        // A sealed file provides a readable futex key without exposing
        // any writable alias or changing the system property area.
        fd = static_cast<int>(syscall(__NR_memfd_create, "property-view",
                                     MFD_CLOEXEC | MFD_ALLOW_SEALING));
        if (fd < 0) { failureStage.store(1); return nullptr; }
        if (ftruncate(fd, capacity)) { failureStage.store(2); close(fd); return nullptr; }
        flags = MAP_SHARED;
#endif
        void *memory = mmap(nullptr, capacity, PROT_READ | PROT_WRITE, flags, fd, 0);
        if (memory == MAP_FAILED) { failureStage.store(3); if (fd >= 0) close(fd); return nullptr; }
        auto *bytes = static_cast<char *>(memory);
        uint32_t serial = static_cast<uint32_t>(isLong ? sizeof(compatibility) - 1 : value.size()) << 24;
        if (isLong) serial |= longFlag;
        // Construct an actual atomic header before making the object read-only.
        static_assert(sizeof(std::atomic<uint32_t>) == 4, "property serial size");
        new (memory) std::atomic<uint32_t>(serial);
        memcpy(bytes + headerSize, name.c_str(), name.size() + 1);
        if (isLong) {
            memcpy(bytes + valueOffset, compatibility, sizeof(compatibility));
            uint32_t relative = static_cast<uint32_t>(offset);
            memcpy(bytes + longOffset, &relative, sizeof(relative));
            memcpy(bytes + offset, value.c_str(), value.size() + 1);
        } else memcpy(bytes + valueOffset, value.c_str(), value.size() + 1);
#ifdef __ANDROID__
        munmap(memory, capacity);
        if (fcntl(fd, F_ADD_SEALS, F_SEAL_WRITE | F_SEAL_GROW | F_SEAL_SHRINK | F_SEAL_SEAL)) {
            failureStage.store(4); close(fd); return nullptr;
        }
        // Android rejects a new shared mapping of this sealed writable FD.
        // A read-only private file mapping still supplies the file-backed
        // shared-futex key; it must not be an anonymous private mapping.
        memory = mmap(nullptr, capacity, PROT_READ, MAP_PRIVATE, fd, 0);
        close(fd);
        if (memory == MAP_FAILED) { failureStage.store(5); return nullptr; }
#else
        if (mprotect(memory, capacity, PROT_READ)) {
            failureStage.store(6);
            munmap(memory, capacity);
            return nullptr;
        }
#endif
        objects_.emplace(std::move(key), memory);
        owned_.insert(memory);
        return memory;
    }
};
}
