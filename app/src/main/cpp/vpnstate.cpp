#include "vector-hooks.h"
#include <ifaddrs.h>
#include <cstdlib>
#include <mutex>
#include <unordered_map>
namespace {
int (*real_getifaddrs)(ifaddrs **) = nullptr;
void (*real_freeifaddrs)(ifaddrs *) = nullptr;
std::mutex listsMutex;
std::unordered_map<ifaddrs *, ifaddrs *> lists;
bool tunnel(const char *name) {
    if (!name) return false;
    for (const char *prefix : {"tun", "tap", "ppp", "ipsec", "vti", "wg", "utun"}) {
        size_t size = strlen(prefix);
        if (!strncmp(name, prefix, size) && name[size] >= '0' && name[size] <= '9') return true;
    }
    return !strcmp(name, "utun");
}
void h_freeifaddrs(ifaddrs *head) {
    ifaddrs *original = nullptr;
    {
        std::lock_guard lock(listsMutex);
        auto entry = lists.find(head);
        if (entry != lists.end()) { original = entry->second; lists.erase(entry); }
    }
    if (!original) { real_freeifaddrs(head); return; }
    while (head) { auto *next = head->ifa_next; free(head); head = next; }
    real_freeifaddrs(original);
}
int h_getifaddrs(ifaddrs **output) {
    int result = real_getifaddrs(output);
    if (result || !output || !*output) return result;
    ifaddrs *original = *output, *head = nullptr, **tail = &head;
    bool filtered = false;
    for (auto *item = original; item; item = item->ifa_next) {
        if (tunnel(item->ifa_name)) { filtered = true; continue; }
        auto *copy = static_cast<ifaddrs *>(malloc(sizeof(ifaddrs)));
        if (!copy) {
            while (head) { auto *next = head->ifa_next; free(head); head = next; }
            // Allocation failure retains the valid original result.
            return result;
        }
        *copy = *item;
        copy->ifa_next = nullptr;
        *tail = copy;
        tail = &copy->ifa_next;
    }
    if (!filtered) {
        while (head) { auto *next = head->ifa_next; free(head); head = next; }
        return result;
    }
    if (head) { std::lock_guard lock(listsMutex); lists.emplace(head, original); }
    else real_freeifaddrs(original);
    *output = head;
    return result;
}
}
extern "C" __attribute__((visibility("default"))) OnLoad native_init(const NativeAPIEntries *api) {
    if (!api || api->version < 1 || !api->hookFunc) return nullptr;
    anonymizeLinkerFileViews();
    // Install the paired free hook first so cloned list ownership always has a matching destructor.
    if (install(api, "freeifaddrs", h_freeifaddrs, &real_freeifaddrs))
        install(api, "getifaddrs", h_getifaddrs, &real_getifaddrs);
    __android_log_print(ANDROID_LOG_INFO, "VpnStateShield", "native ready hooks=%d", hookCount.load());
    return nullptr;
}
extern "C" __attribute__((visibility("default"))) jint JNI_OnLoad(JavaVM *, void *) {
    return JNI_VERSION_1_6;
}
