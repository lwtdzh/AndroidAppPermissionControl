#pragma once

#include <sys/system_properties.h>
#include <algorithm>
#include <cerrno>
#include <cstring>
#include <string>

namespace shield_properties {
using Callback = void (*)(void *, const char *, const char *, uint32_t);
using ReadCallback = void (*)(const prop_info *, Callback, void *);
using HandleMapper = const prop_info *(*)(const prop_info *);
using HandleOwner = bool (*)(const prop_info *);

struct HandleAdapter {
    HandleMapper map = nullptr;
    HandleOwner owns = nullptr;
};

struct Snapshot {
    std::string name, value;
    bool captured = false;
};

// The callback is synchronous and supplies the untruncated name. Use the
// owning library's original trampoline, not the hooked public callback entry.
inline Snapshot snapshot(const prop_info *info, ReadCallback original) {
    Snapshot result;
    int saved = errno;
    if (info && original) original(info, [](void *cookie, const char *name,
                                           const char *value, uint32_t) {
        auto &out = *static_cast<Snapshot *>(cookie);
        out.name = name;
        out.value = value;
        out.captured = true;
    }, &result);
    errno = saved;
    return result;
}

// Bionic's legacy APIs cannot return a long read-only value. Its long-property
// compatibility slot contains this message; the callback still gets the value.
inline int writeLegacy(const char *name, const std::string &replacement, char *output) {
    static constexpr char longValue[] = "Must use __system_property_read_callback() to read";
    bool longReadOnly = name && !std::strncmp(name, "ro.", 3) &&
                       replacement.size() >= PROP_VALUE_MAX;
    const char *data = longReadOnly ? longValue : replacement.data();
    size_t length = longReadOnly ? sizeof(longValue) - 1 :
                    std::min(replacement.size(), static_cast<size_t>(PROP_VALUE_MAX - 1));
    // Remove the original value's tail too: callers own the entire legacy slot.
    std::memset(output, 0, PROP_VALUE_MAX);
    std::memcpy(output, data, length);
    return static_cast<int>(length);
}
}
