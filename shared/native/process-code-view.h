#pragma once
#include <sys/uio.h>
#include <algorithm>
#include <cstdint>

namespace shield_code {
// 内核把两组 iovec 各自串联；两边的分段位置不一定相同。
template<class Overlay>
void overlayRead(const iovec *local, size_t localCount, const iovec *remote,
                 size_t remoteCount, ssize_t copied, Overlay overlay) {
    if (copied <= 0) return;
    size_t l = 0, r = 0, lo = 0, ro = 0, remaining = static_cast<size_t>(copied);
    while (remaining && l < localCount && r < remoteCount) {
        if (lo == local[l].iov_len) { ++l; lo = 0; continue; }
        if (ro == remote[r].iov_len) { ++r; ro = 0; continue; }
        size_t n = std::min({remaining, local[l].iov_len - lo, remote[r].iov_len - ro});
        uintptr_t at = reinterpret_cast<uintptr_t>(remote[r].iov_base);
        uintptr_t out = reinterpret_cast<uintptr_t>(local[l].iov_base);
        if (ro > UINTPTR_MAX - at || lo > UINTPTR_MAX - out
            || n > UINTPTR_MAX - (at + ro) || n > UINTPTR_MAX - (out + lo)) return;
        overlay(at + ro, reinterpret_cast<void *>(out + lo), n);
        remaining -= n; lo += n; ro += n;
    }
}
}
