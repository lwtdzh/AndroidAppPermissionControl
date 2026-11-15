#pragma once
#include "property-area.h"
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <linux/memfd.h>
#include <cerrno>
#include "device-raw-io.h"

namespace device_files {
inline thread_local bool internal = false;
struct Guard { bool old = internal; Guard(){internal=true;} ~Guard(){internal=old;} };
inline std::string path(int fd) {
    char buffer[4096];
    std::string link="/proc/self/fd/"+std::to_string(fd);
    ssize_t n=readlink(link.c_str(),buffer,sizeof(buffer));
    return n>0 ? std::string(buffer,n) : "";
}
inline bool propertyPath(const std::string &name) { return name.rfind("/dev/__properties__/",0)==0; }
inline bool ownMemory(const std::string &name) {
    return name=="/proc/self/mem" || name=="/proc/"+std::to_string(getpid())+"/mem";
}
inline bool load(int fd, shield_properties::Area &area) {
    struct stat metadata{};
    if(fstat(fd,&metadata) || !S_ISREG(metadata.st_mode) || metadata.st_size<240 ||
       metadata.st_size>16*1024*1024)return false;
    std::vector<uint8_t> buffer(metadata.st_size);
    for(int attempt=0;attempt<3;++attempt) {
        size_t at=0;
        while(at<buffer.size()) {
            ssize_t n=device_io::pread(fd,buffer.data()+at,buffer.size()-at,at);
            if(n<0 && errno==EINTR)continue;
            if(n<=0)break;
            at+=n;
        }
        uint32_t serial=0;
        if(at==buffer.size() && device_io::pread(fd,&serial,4,4)==4 &&
           !memcmp(buffer.data()+4,&serial,4) && area.load(buffer.data(),buffer.size()))return true;
    }
    return false;
}
inline int sealed(const std::vector<uint8_t> &bytes) {
    int fd=static_cast<int>(syscall(__NR_memfd_create,"property-area",MFD_CLOEXEC|MFD_ALLOW_SEALING));
    if(fd<0)return -1;
    size_t at=0;
    while(at<bytes.size()) {
        ssize_t n=pwrite64(fd,bytes.data()+at,bytes.size()-at,at);
        if(n<0 && errno==EINTR)continue;
        if(n<=0){close(fd);return -1;}
        at+=n;
    }
    if(fcntl(fd,F_ADD_SEALS,F_SEAL_WRITE|F_SEAL_GROW|F_SEAL_SHRINK|F_SEAL_SEAL)) {
        close(fd);return -1;
    }
    // Android SELinux denies reopening appdomain_tmpfs via /proc/self/fd.
    // Keep this sealed descriptor private to the module and map it PRIVATE.
    // App descriptors retain their original access mode and file position.
    return fd;
}
}
