#include "vector-hooks.h"
#include "loaded-symbol.h"
#include "property-read.h"
#include "property-view.h"
#include "device-file-view.h"
#include "device-syscall-view.h"
#include <cstdarg>
#include <sys/uio.h>
#include <android/api-level.h>
#include <sys/system_properties.h>
#include <ifaddrs.h>
#include <linux/if_packet.h>
#include <memory>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#include <algorithm>
#include <dirent.h>

namespace {
using Values = std::unordered_map<std::string,std::string>;
std::shared_ptr<const Values> values = std::make_shared<const Values>();
NativeAPIEntries entries{};
using PropertyCallback = void (*)(void *, const char *, const char *, uint32_t);
int (*real_get)(const char *, char *) = nullptr;
int (*real_read)(const prop_info *, char *, char *) = nullptr;
void (*real_callback)(const prop_info *, PropertyCallback, void *) = nullptr;
int (*real_getifaddrs)(ifaddrs **) = nullptr;
const prop_info *(*real_find)(const char *) = nullptr;
const prop_info *(*real_nth)(unsigned) = nullptr;
using EachCallback = void (*)(const prop_info *, void *);
int (*real_foreach)(EachCallback, void *) = nullptr;
shield_properties::ReadOnlyViews views;
std::atomic<bool> objectReady{false};
int (*real_open)(const char *,int,...) = nullptr;
int (*real_openat)(int,const char *,int,...) = nullptr;
int (*real_open_2)(const char *,int) = nullptr;
int (*real_openat_2)(int,const char *,int) = nullptr;
FILE *(*real_fopen)(const char *,const char *) = nullptr;
ssize_t (*real_pread64)(int,void *,size_t,off64_t) = nullptr;
ssize_t (*real_readfd)(int,void *,size_t) = nullptr;
ssize_t (*real_readvfd)(int,const iovec *,int) = nullptr;
std::atomic<int> fileViews{0}, remappedPages{0}, retainedPages{0};
struct PropertyMapping{uintptr_t start;size_t size;std::string path;std::vector<size_t> pages;};
std::vector<PropertyMapping> propertyMappings;
std::mutex mappingsMutex;
using CodeOverlay=void (*)(uintptr_t,void *,size_t);
std::vector<CodeOverlay> brokerOverlays;
struct FileSnapshot {
    uint64_t device,inode;int descriptor;
    std::vector<uint8_t> bytes;
    std::vector<std::pair<size_t,size_t>> changed;
    uint64_t shadowDevice,shadowInode;
};
struct MappedSnapshot{uintptr_t start;size_t size;size_t file;};
struct BrokerSnapshot {
    std::vector<FileSnapshot> files;
    std::vector<MappedSnapshot> mappings;
    ~BrokerSnapshot(){for(auto &file:files)device_io::close(file.descriptor);}
};
std::shared_ptr<const BrokerSnapshot> brokerSnapshot=std::make_shared<const BrokerSnapshot>();
// This callback consumes a duplicate and returns -1 when unselected. It never
// allocates: the immutable file snapshots were prepared on the update thread.
int brokerOpened(int fd) {
    if(fd<0)return -1;
    struct stat st{};if(device_io::stat(fd,&st)){device_io::close(fd);return -1;}
    auto snapshot=std::atomic_load(&brokerSnapshot);
    for(const auto &file:snapshot->files)
        if((st.st_dev==file.device && st.st_ino==file.inode) ||
           (st.st_dev==file.shadowDevice && st.st_ino==file.shadowInode)) {
            int flags=device_io::fcntl(fd,F_GETFL);
            if(flags<0 || (flags&O_ACCMODE)!=O_RDONLY || (flags&O_PATH))break;
            int next=device_io::duplicate(file.descriptor);
            device_io::close(fd);return next;
        }
    char path[64],name[128];snprintf(path,sizeof(path),"/proc/self/fd/%d",fd);
    ssize_t n=device_io::link(path,name,sizeof(name)-1);
    if(n>0) {
        name[n]=0;char own[64];snprintf(own,sizeof(own),"/proc/%d/mem",getpid());
        if(!strcmp(name,own) || !strcmp(name,"/proc/self/mem"))return fd;
    }
    device_io::close(fd);return -1;
}
void brokerReadView(int fd,void *buffer,ssize_t count,off64_t offset) {
    if(count<=0 || offset<0)return;
    struct stat st{};if(device_io::stat(fd,&st))return;
    auto snapshot=std::atomic_load(&brokerSnapshot);
    auto overlay=[&](const FileSnapshot &file,size_t from,size_t n,void *out) {
        if(n>SIZE_MAX-from)return;
        for(auto [at,size]:file.changed) {
            size_t begin=std::max(from,at),end=std::min(from+n,at+size);
            if(begin<end)memcpy(static_cast<char *>(out)+begin-from,file.bytes.data()+begin,end-begin);
        }
    };
    for(const auto &file:snapshot->files)if(st.st_dev==file.device && st.st_ino==file.inode) {
        if(static_cast<uint64_t>(offset)<file.bytes.size()) {
            size_t n=std::min(static_cast<size_t>(count),file.bytes.size()-static_cast<size_t>(offset));
            overlay(file,offset,n,buffer);
        }
        return;
    }
    uintptr_t begin=static_cast<uintptr_t>(offset);
    if(static_cast<size_t>(count)>UINTPTR_MAX-begin)return;
    for(const auto &mapping:snapshot->mappings) {
        uintptr_t from=std::max(begin,mapping.start),end=std::min(begin+count,mapping.start+mapping.size);
        if(from>=end)continue;
        const auto &bytes=snapshot->files[mapping.file].bytes;
        if(end-mapping.start<=bytes.size())
            overlay(snapshot->files[mapping.file],from-mapping.start,end-from,
                static_cast<char *>(buffer)+from-begin);
    }
    codeViews.overlay(begin,buffer,count);
    for(auto overlay:brokerOverlays)overlay(begin,buffer,count);
}
void prepareBrokerSnapshot(const std::shared_ptr<const Values> &values) {
    auto next=std::make_shared<BrokerSnapshot>();
    if(!values->empty()) {
        std::unordered_set<std::string> paths;
        for(const auto &mapping:propertyMappings)paths.insert(mapping.path);
        DIR *directory=opendir("/dev/__properties__");
        if(directory) {
            while(auto *entry=readdir(directory)) {
                if(entry->d_name[0]=='.')continue;
                paths.insert("/dev/__properties__/"+std::string(entry->d_name));
            }
            closedir(directory);
        }
        for(const auto &path:paths) {
                int source=device_io::open(path.c_str(),O_RDONLY|O_CLOEXEC);if(source<0)continue;
                struct stat st{};shield_properties::Area area;
                bool valid=!fstat(source,&st) && device_files::load(source,area) &&
                    area.replace(*values) && !area.changed.empty();
                close(source);if(!valid)continue;
                int shadow=device_files::sealed(area.bytes());struct stat shadowStat{};
                if(shadow<0)continue;
                if(fstat(shadow,&shadowStat)){close(shadow);continue;}
                size_t index=next->files.size();
                next->files.push_back({st.st_dev,st.st_ino,shadow,area.bytes(),area.changed,shadowStat.st_dev,shadowStat.st_ino});
                for(const auto &mapping:propertyMappings)if(mapping.path==path)
                    next->mappings.push_back({mapping.start,mapping.size,index});
        }
    }
    std::atomic_store(&brokerSnapshot,std::shared_ptr<const BrokerSnapshot>(next));
}
int opened(int fd) {
    if(fd<0 || device_files::internal)return fd;
    int saved=errno; device_files::Guard guard;
    auto snapshot=std::atomic_load(&values);
    if(snapshot->empty() || !device_files::propertyPath(device_files::path(fd))) {errno=saved;return fd;}
    // Keep the application's original descriptor. Reads are overlaid and the
    // synchronized syscall broker substitutes only read-only mmap backing.
    ++fileViews;errno=saved;return fd;
}
void readView(int fd,void *buffer,ssize_t count,off64_t offset) {
    if(device_files::internal || count<=0 || offset<0)return;
    int saved=errno;device_files::Guard guard;
    auto snapshot=std::atomic_load(&values);
    if(snapshot->empty()){errno=saved;return;}
    auto name=device_files::path(fd);
    if(device_files::ownMemory(name)) {
        {
            std::lock_guard<std::mutex> lock(mappingsMutex);
            uintptr_t begin=static_cast<uintptr_t>(offset);
            if(static_cast<size_t>(count)<=UINTPTR_MAX-begin)
                for(const auto &mapping:propertyMappings) {
                    uintptr_t from=std::max(begin,mapping.start);
                    uintptr_t end=std::min(begin+count,mapping.start+mapping.size);
                    if(from>=end)continue;
                    int source=device_io::open(mapping.path.c_str(),O_RDONLY|O_CLOEXEC);if(source<0)continue;
                    shield_properties::Area area;
                    bool valid=device_files::load(source,area);close(source);
                    if(valid && area.replace(*snapshot) && end-mapping.start<=area.bytes().size())
                        memcpy(static_cast<char *>(buffer)+from-begin,
                            area.bytes().data()+from-mapping.start,end-from);
                }
        }
        using Overlay=void (*)(uintptr_t,void *,size_t);
        codeViews.overlay(static_cast<uintptr_t>(offset),buffer,count);
        for(const char *library:{"libshield.so","libdeveloperstate.so","libselinuxstate.so","libvpnstate.so"}) {
            auto overlay=reinterpret_cast<Overlay>(loadedSymbol(library,"appstateshield_overlay_own_code"));
            if(overlay)overlay(static_cast<uintptr_t>(offset),buffer,count);
        }
    } else if(device_files::propertyPath(name)) {
        shield_properties::Area area;
        if(device_files::load(fd,area) && area.replace(*snapshot) &&
           static_cast<uint64_t>(offset)<area.bytes().size()) {
            size_t n=std::min(static_cast<size_t>(count),area.bytes().size()-static_cast<size_t>(offset));
            memcpy(buffer,area.bytes().data()+offset,n);
        }
    }
    errno=saved;
}
bool modeRequired(int flags){return (flags&O_CREAT) || ((flags&O_TMPFILE)==O_TMPFILE);}
int h_openfd(const char *name,int flags,...) {
    mode_t mode=0;if(modeRequired(flags)){va_list ap;va_start(ap,flags);mode=va_arg(ap,int);va_end(ap);}
    return opened(real_open(name,flags,mode));
}
int h_openatfd(int dir,const char *name,int flags,...) {
    mode_t mode=0;if(modeRequired(flags)){va_list ap;va_start(ap,flags);mode=va_arg(ap,int);va_end(ap);}
    return opened(real_openat(dir,name,flags,mode));
}
int h_open2fd(const char *name,int flags){return opened(real_open_2(name,flags));}
int h_openat2fd(int dir,const char *name,int flags){return opened(real_openat_2(dir,name,flags));}
FILE *h_fopenfd(const char *name,const char *mode) {
    FILE *stream=real_fopen(name,mode);
    if(stream) {
        int fd=fileno(stream);
        // opened consumes its original. Duplicate so the FILE's descriptor
        // remains valid until dup3 atomically replaces it.
        int copy=dup(fd),next=opened(copy);
        if(next>=0){int flags=fcntl(next,F_GETFD);dup3(next,fd,flags&FD_CLOEXEC?O_CLOEXEC:0);close(next);}
    }
    return stream;
}
ssize_t h_preadfd(int fd,void *buffer,size_t n,off64_t at) {
    ssize_t result=real_pread64(fd,buffer,n,at);readView(fd,buffer,result,at);return result;
}
ssize_t h_readfd(int fd,void *buffer,size_t n) {
    ssize_t result=real_readfd(fd,buffer,n);
    if(result>0){int saved=errno;off64_t end=lseek64(fd,0,SEEK_CUR);errno=saved;readView(fd,buffer,result,end-result);}
    return result;
}
ssize_t h_readvfd(int fd,const iovec *iov,int count) {
    ssize_t result=real_readvfd(fd,iov,count);
    if(result>0) {
        int saved=errno;off64_t at=lseek64(fd,0,SEEK_CUR)-result;errno=saved;
        size_t remaining=result;
        for(int i=0;i<count && remaining;++i) {
            size_t n=std::min(remaining,iov[i].iov_len);
            readView(fd,iov[i].iov_base,n,at);at+=n;remaining-=n;
        }
    }
    return result;
}
// Only pages free of mutable properties can be privately remapped. Keep
// addresses stable so callers that cached original prop_info pointers see
// the substituted payload too. Never replace the shared area header.
void remapAreas(const std::shared_ptr<const Values> &snapshot) {
    device_files::Guard guard;
    std::lock_guard<std::mutex> lock(mappingsMutex);
    if(propertyMappings.empty()) {
    FILE *maps=fopen("/proc/self/maps","r");
    if(!maps)return;
    char line[PATH_MAX+256];
    while(fgets(line,sizeof(line),maps)) {
        uintptr_t start=0,end=0;unsigned long offset=0;char permissions[5]{},path[PATH_MAX]{};
        if(sscanf(line,"%" SCNxPTR "-%" SCNxPTR " %4s %lx %*s %*s %4095s",
            &start,&end,permissions,&offset,path)!=5 || strcmp(permissions,"r--s") ||
            offset || end<=start || !device_files::propertyPath(path))continue;
        propertyMappings.push_back({start,end-start,path,{}});
    }
    fclose(maps);
    }
    long page=sysconf(_SC_PAGESIZE);if(page<=0)return;
    remappedPages.store(0);retainedPages.store(0);
    for(auto &mapping:propertyMappings) {
        int fd=device_io::open(mapping.path.c_str(),O_RDONLY|O_CLOEXEC);if(fd<0)continue;
        // Restore original shared pages before computing a new immutable view.
        // This also restores direct pointers when fields/master are deselected.
        std::vector<size_t> unrestored;
        for(size_t at:mapping.pages) if(device_io::map(reinterpret_cast<void *>(mapping.start+at),page,PROT_READ,
            MAP_SHARED|MAP_FIXED,fd,at)==MAP_FAILED)unrestored.push_back(at);
        mapping.pages=std::move(unrestored);
        shield_properties::Area area;
        bool valid=device_files::load(fd,area);close(fd);
        if(!valid || area.bytes().size()!=mapping.size || !area.replace(*snapshot,true))continue;
        auto pages=area.immutablePages(page);
        std::unordered_set<size_t> wanted;
        for(auto [at,n]:area.changed) for(size_t p=at/page*page;p<(at+n+page-1)/page*page;p+=page)
            wanted.insert(p);
        retainedPages+=static_cast<int>(wanted.size()-pages.size());
        int shadow=device_files::sealed(area.bytes());if(shadow<0)continue;
        for(size_t at:pages) {
            if(at+page>mapping.size)continue;
            if(device_io::map(reinterpret_cast<void *>(mapping.start+at),page,PROT_READ,
                MAP_PRIVATE|MAP_FIXED,shadow,at)!=MAP_FAILED){++remappedPages;mapping.pages.push_back(at);}
        }
        close(shadow);
    }
}
const shield_properties::HandleAdapter *handleAdapter();

const prop_info *selected(const char *name, const prop_info *original,
                          const std::shared_ptr<const Values> &snapshot) {
    if (!objectReady.load() || !name || strncmp(name, "ro.", 3)) return original;
    auto found = snapshot->find(name);
    if (found == snapshot->end()) return original;
    auto *shadow = static_cast<const prop_info *>(views.get(name, found->second));
    if (!shadow) {
        __android_log_print(ANDROID_LOG_WARN,"DeviceProfile","property object allocation failed stage=%d errno=%d",
                            views.failureStage.load(),errno);
        objectReady.store(false); // Text fallback remains; status reports the failure.
    }
    return shadow ? shadow : original;
}
const prop_info *mapHandle(const prop_info *info) {
    if (!info || views.owns(info)) return info;
    std::string name = views.name(info);
    return name.empty() ? info : selected(name.c_str(), info, std::atomic_load(&values));
}
bool ownsHandle(const prop_info *info) { return views.owns(info); }
const shield_properties::HandleAdapter *handleAdapter() {
    static const shield_properties::HandleAdapter adapter{mapHandle, ownsHandle};
    return &adapter;
}
const prop_info *h_find(const char *name) {
    const prop_info *info = real_find(name);
    views.remember(info, name);
    return selected(name, info, std::atomic_load(&values));
}
struct EachContext {
    EachCallback callback;
    void *cookie;
    std::shared_ptr<const Values> snapshot;
    std::unordered_set<std::string> seen;
    unsigned count = 0;
};
void each(const prop_info *info, void *cookie) {
    auto &context = *static_cast<EachContext *>(cookie);
    auto source = shield_properties::snapshot(info, real_callback);
    if (source.captured) {
        views.remember(info, source.name.c_str());
        context.seen.insert(source.name);
    }
    ++context.count;
    if (context.callback) context.callback(
        source.captured ? selected(source.name.c_str(), info, context.snapshot) : info, context.cookie);
}
void appendMissing(EachContext &context) {
    if (!objectReady.load()) return;
    std::vector<std::string> names;
    for (const auto &entry : *context.snapshot)
        if (!entry.first.compare(0, 3, "ro.") && !context.seen.count(entry.first))
            names.push_back(entry.first);
    std::sort(names.begin(), names.end());
    for (const auto &name : names) {
        auto *info = selected(name.c_str(), nullptr, context.snapshot);
        if (info) { ++context.count; if (context.callback) context.callback(info, context.cookie); }
    }
}
int h_foreach(EachCallback function, void *cookie) {
    EachContext context{function, cookie, std::atomic_load(&values), {}};
    int result = real_foreach(each, &context);
    if (!result) appendMissing(context);
    return result;
}
const prop_info *h_nth(unsigned index) {
    if (auto *info = real_nth(index)) return mapHandle(info);
    // Stock ordering remains intact; only synthesize indexes beyond its end.
    EachContext context{nullptr, nullptr, std::atomic_load(&values), {}};
    if (real_foreach(each, &context)) return nullptr;
    unsigned stockCount = context.count;
    struct Search { unsigned index, position; const prop_info *found = nullptr; };
    Search search{index, stockCount};
    context.callback = [](const prop_info *info, void *cookie) {
        auto &out = *static_cast<Search *>(cookie);
        if (out.position++ == out.index) out.found = info;
    };
    context.cookie = &search;
    appendMissing(context);
    return search.found;
}

const char *property(const char *name,const char *original) {
    if (!name) return original;
    auto snapshot = std::atomic_load(&values);
    auto found = snapshot->find(name);
    if (found == snapshot->end()) return original;
    // The caller copies this value synchronously. Never return a pointer into a
    // snapshot that a concurrent profile update can release.
    thread_local std::string result;
    result = found->second;
    return result.c_str();
}
int replace(const char *name,char *buffer,int original) {
    std::string next = property(name,buffer);
    if (next == buffer) return original;
    return shield_properties::writeLegacy(name,next,buffer);
}
int h_get(const char *name,char *buffer) { int n=real_get(name,buffer);return replace(name,buffer,n); }
int h_read(const prop_info *info,char *name,char *buffer) {
    info=mapHandle(info);
    if(ownsHandle(info)) {
        int result=real_read(info,name,buffer);
        auto source=shield_properties::snapshot(info,real_callback);
        return source.captured ? shield_properties::writeLegacy(source.name.c_str(),source.value,buffer) : result;
    }
    int n=real_read(info,name,buffer);
    auto source=shield_properties::snapshot(info,real_callback);
    if(!source.captured)return n;
    std::string replacement=property(source.name.c_str(),source.value.c_str());
    return replacement==source.value?n:
        shield_properties::writeLegacy(source.name.c_str(),replacement,buffer);
}
struct CallbackContext { PropertyCallback callback;void *cookie; };
void callback(void *cookie,const char *name,const char *value,uint32_t serial) {
    auto *context=static_cast<CallbackContext *>(cookie);
    std::string replacement=property(name,value);
    context->callback(context->cookie,name,replacement.c_str(),serial);
}
void h_callback(const prop_info *info,PropertyCallback function,void *cookie) {
    info=mapHandle(info);
    if(ownsHandle(info)) { real_callback(info,function,cookie);return; }
    CallbackContext context{function,cookie};real_callback(info,callback,&context);
}
void interfaces(ifaddrs *list) {
    auto snapshot=std::atomic_load(&values);
    auto found=snapshot->find("wifi_mac");if(found==snapshot->end())return;
    unsigned address[6];
    if (sscanf(found->second.c_str(),"%x:%x:%x:%x:%x:%x",&address[0],&address[1],&address[2],&address[3],&address[4],&address[5])!=6)return;
    for (auto *item=list;item;item=item->ifa_next) {
        if(!item->ifa_name || !item->ifa_addr || item->ifa_addr->sa_family!=AF_PACKET)continue;
        if(strncmp(item->ifa_name,"wlan",4) && strncmp(item->ifa_name,"eth",3))continue;
        auto *link=reinterpret_cast<sockaddr_ll *>(item->ifa_addr);
        if(link->sll_halen!=6)continue;
        for(size_t i=0;i<6;i++)link->sll_addr[i]=static_cast<unsigned char>(address[i]);
    }
}
int h_getifaddrs(ifaddrs **output) {
    int result=real_getifaddrs(output);
    if(!result && output && *output)interfaces(*output);
    return result;
}
bool externalRedirect(void *symbol) {
#if defined(__aarch64__)
    uint32_t words[2];memcpy(words,symbol,sizeof(words));uintptr_t target=0;
    if((words[0]&0xfc000000u)==0x14000000u){
        int64_t offset=words[0]&0x03ffffffu;if(offset&0x02000000)offset-=0x04000000;
        target=reinterpret_cast<uintptr_t>(symbol)+offset*4;
    }else if((words[0]&0xffffffe0u)==0x58000040u && (words[1]&0xfffffc1fu)==0xd61f0000u
        && (words[0]&31u)==((words[1]>>5)&31u))memcpy(&target,static_cast<char *>(symbol)+8,sizeof(target));
    if(!target)return false;
    Dl_info from{},to{};
    return !dladdr(symbol,&from) || !dladdr(reinterpret_cast<void *>(target),&to) || from.dli_fbase!=to.dli_fbase;
#else
    (void)symbol;return false;
#endif
}
template<class R,class O> void add(const char *name,R replacement,O *original) {
    void *symbol=dlsym(RTLD_DEFAULT,name);
    if(!symbol || symbolSize(symbol,name)<16 || externalRedirect(symbol)) {
        __android_log_print(ANDROID_LOG_WARN,"DeviceProfile","native entry retained: %s",name);return;
    }
    install(&entries,name,replacement,original);
}
template<class R,class O> void addProperty(const char *name,R replacement,O *original) {
    void *symbol=dlsym(RTLD_DEFAULT,name);
    using Register=bool (*)(void *,const char *(*)(const char *,const char *));
    for(const char *library:{"libdeveloperstate.so","libselinuxstate.so"}) {
        auto registration=reinterpret_cast<Register>(loadedSymbol(library,"appstateshield_set_device_property_filter"));
        if(registration && registration(symbol,property))return;
    }
    add(name,replacement,original);
}
template<class R,class O> void addFile(const char *name,R replacement,O *original,int kind) {
    using Register=bool (*)(void *,int,int (*)(int),void (*)(int,void *,ssize_t,off64_t));
    auto registration=reinterpret_cast<Register>(
        loadedSymbol("libshield.so","appstateshield_set_device_file_views"));
    if(registration && registration(dlsym(RTLD_DEFAULT,name),kind,opened,readView))return;
    add(name,replacement,original);
}
bool verifyLayout() {
    int sdk=android_get_device_api_level();
    if(sdk<27 || sdk>36 || !real_find || !real_callback || !real_foreach)return false;
    auto *info=real_find("ro.product.model");
    auto source=shield_properties::snapshot(info,real_callback);
    if(!source.captured || source.name!="ro.product.model" || source.value.size()>=PROP_VALUE_MAX)return false;
    const char *raw=reinterpret_cast<const char *>(info);
    uint32_t serial=0;memcpy(&serial,raw,4);
    return serial==source.value.size()<<24 &&
        !memcmp(raw+96,source.name.c_str(),source.name.size()+1) &&
        !memcmp(raw+4,source.value.c_str(),source.value.size()+1);
}
}
extern "C" __attribute__((visibility("default"))) OnLoad native_init(const NativeAPIEntries *api) {
    if(!api || api->version<1 || !api->hookFunc)return nullptr;
    entries=*api;anonymizeLinkerFileViews();
    // Keep a callable original reader even if the callback entry must be retained.
    real_callback=reinterpret_cast<shield_properties::ReadCallback>(
        dlsym(RTLD_DEFAULT,"__system_property_read_callback"));
    real_find=reinterpret_cast<decltype(real_find)>(dlsym(RTLD_DEFAULT,"__system_property_find"));
    real_foreach=reinterpret_cast<decltype(real_foreach)>(dlsym(RTLD_DEFAULT,"__system_property_foreach"));
    if(verifyLayout()) {
        // Index original objects before publishing any mapper to other owners.
        EachContext index{nullptr,nullptr,std::atomic_load(&values),{}};
        if(!real_foreach(each,&index)) objectReady.store(true);
    }
    addProperty("__system_property_get",h_get,&real_get);
    addProperty("__system_property_read",h_read,&real_read);
    addProperty("__system_property_read_callback",h_callback,&real_callback);
    using RegisterHandles=void (*)(const shield_properties::HandleAdapter *);
    for(const char *library:{"libdeveloperstate.so","libselinuxstate.so"}) {
        auto registration=reinterpret_cast<RegisterHandles>(
            loadedSymbol(library,"appstateshield_set_device_property_handles"));
        if(registration)registration(handleAdapter());
    }
    if(objectReady.load()) {
        add("__system_property_find",h_find,&real_find);
        add("__system_property_foreach",h_foreach,&real_foreach);
        add("__system_property_find_nth",h_nth,&real_nth);
        objectReady.store(hookedSymbols.count(dlsym(RTLD_DEFAULT,"__system_property_find")) &&
            hookedSymbols.count(dlsym(RTLD_DEFAULT,"__system_property_foreach")) &&
            hookedSymbols.count(dlsym(RTLD_DEFAULT,"__system_property_find_nth")));
    }
    using Register=bool (*)(void *,void (*)(ifaddrs *));
    auto registration=reinterpret_cast<Register>(loadedSymbol("libvpnstate.so","appstateshield_set_device_interface_filter"));
    if(!registration || !registration(dlsym(RTLD_DEFAULT,"getifaddrs"),interfaces))
        add("getifaddrs",h_getifaddrs,&real_getifaddrs);
    addFile("open",h_openfd,&real_open,0);
    addFile("openat",h_openatfd,&real_openat,0);
    addFile("__open_2",h_open2fd,&real_open_2,0);
    addFile("__openat_2",h_openat2fd,&real_openat_2,0);
    addFile("fopen",h_fopenfd,&real_fopen,0);
    addFile("pread64",h_preadfd,&real_pread64,1);
    addFile("read",h_readfd,&real_readfd,1);
    addFile("readv",h_readvfd,&real_readvfd,1);
    for(const char *library:{"libshield.so","libdeveloperstate.so","libselinuxstate.so","libvpnstate.so"}) {
        auto overlay=reinterpret_cast<CodeOverlay>(loadedSymbol(library,"appstateshield_overlay_own_code"));
        if(overlay)brokerOverlays.push_back(overlay);
    }
    __android_log_print(ANDROID_LOG_INFO,"DeviceProfile","native ready hooks=%d objects=%d",hookCount.load(),objectReady.load());
    return nullptr;
}
extern "C" __attribute__((visibility("default"))) JNIEXPORT void JNICALL
Java_io_github_lwtdzh_appstateshield_DeviceRuntime_nativeUpdate(JNIEnv *env,jclass,jobjectArray keys,jobjectArray data) {
    if(!keys || !data || env->GetArrayLength(keys)!=env->GetArrayLength(data))return;
    auto next=std::make_shared<Values>();
    for(jsize i=0;i<env->GetArrayLength(keys);i++){
        auto key=static_cast<jstring>(env->GetObjectArrayElement(keys,i));
        auto value=static_cast<jstring>(env->GetObjectArrayElement(data,i));
        if(key && value){
            const char *k=env->GetStringUTFChars(key,nullptr),*v=env->GetStringUTFChars(value,nullptr);
            if(k && v)(*next)[k]=v;
            if(k)env->ReleaseStringUTFChars(key,k);if(v)env->ReleaseStringUTFChars(value,v);
        }
        env->DeleteLocalRef(key);env->DeleteLocalRef(value);
    }
    std::atomic_store(&values,std::shared_ptr<const Values>(next));
    remapAreas(next);
    prepareBrokerSnapshot(next);
    if(!next->empty())device_syscalls::start(brokerOpened,brokerReadView,[](){return !std::atomic_load(&values)->empty();});
}
extern "C" __attribute__((visibility("default"))) jint JNI_OnLoad(JavaVM *,void *) { return JNI_VERSION_1_6; }
extern "C" JNIEXPORT jboolean JNICALL
Java_io_github_lwtdzh_appstateshield_DeviceRuntime_nativeObjectsReady(JNIEnv *,jclass) {
    return objectReady.load();
}
extern "C" JNIEXPORT jintArray JNICALL
Java_io_github_lwtdzh_appstateshield_DeviceRuntime_nativeDiagnostics(JNIEnv *env,jclass) {
    jint data[]={fileViews.load(),remappedPages.load(),retainedPages.load(),device_syscalls::state.load(),
        device_syscalls::setupErrno.load()};
    auto out=env->NewIntArray(5);if(out)env->SetIntArrayRegion(out,0,5,data);return out;
}
