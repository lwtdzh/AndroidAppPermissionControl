#include <jni.h>
#include <dlfcn.h>
#include <link.h>
#include <dirent.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/system_properties.h>
#include <unistd.h>
#include <cinttypes>
#include <cstring>
#include <vector>
#include <string>
#include <sstream>
#include <cstdio>
#include <sys/uio.h>

namespace {
std::vector<std::pair<std::string,int>> cachedFiles;
long raw(long number,long a=0,long b=0,long c=0,long d=0,long e=0,long f=0) {
#if defined(__aarch64__)
    register long x8 asm("x8")=number,x0 asm("x0")=a,x1 asm("x1")=b,x2 asm("x2")=c;
    register long x3 asm("x3")=d,x4 asm("x4")=e,x5 asm("x5")=f;
    asm volatile("svc #0":"+r"(x0):"r"(x8),"r"(x1),"r"(x2),"r"(x3),"r"(x4),"r"(x5):"memory","cc");
    return x0;
#else
    return syscall(number,a,b,c,d,e,f); // other ABIs compile; no runtime claim
#endif
}
std::string ordinary(const std::string &path) {
    int fd=static_cast<int>(raw(__NR_openat,AT_FDCWD,reinterpret_cast<long>(path.c_str()),O_RDONLY|O_CLOEXEC));
    char bytes[64]{};
    long count=fd>=0?raw(__NR_read,fd,reinterpret_cast<long>(bytes),sizeof(bytes)):-1;
    bool contents=count==32 && !memcmp(bytes,"ordinary-native-file-control-047",32);
    bool eof=fd>=0 && raw(__NR_read,fd,reinterpret_cast<long>(bytes),sizeof(bytes))==0;
    if(fd>=0)close(fd);
    bool bad=raw(__NR_read,-1,reinterpret_cast<long>(bytes),sizeof(bytes))==-EBADF;
    std::ostringstream out;out<<"{\"rawRead\":"<<(contents?"true":"false")
        <<",\"rawEOF\":"<<(eof?"true":"false")<<",\"rawBadFd\":"<<(bad?"true":"false")<<"}";
    return out.str();
}
std::string rawValue(const uint8_t *bytes,size_t size,const std::string &name,size_t *info=nullptr) {
    for(size_t at=128;at+96+name.size()+1<=size;at+=4) {
        if(memcmp(bytes+at+96,name.c_str(),name.size()+1))continue;
        uint32_t serial=0;memcpy(&serial,bytes+at,4);
        size_t value=at+4;
        if(serial&(1u<<16)){uint32_t relative=0;memcpy(&relative,bytes+at+60,4);value=at+relative;}
        if(value>=size)return "";
        auto *zero=static_cast<const uint8_t *>(memchr(bytes+value,0,size-value));
        if(!zero)return "";
        if(info)*info=at;
        return {reinterpret_cast<const char *>(bytes+value),static_cast<size_t>(zero-bytes-value)};
    }
    return "";
}
uintptr_t originalBase(const std::string &path) {
    FILE *maps=fopen("/proc/self/maps","r");if(!maps)return 0;
    char line[8192];uintptr_t base=0;
    while(fgets(line,sizeof(line),maps)) {
        uintptr_t start=0,end=0;unsigned long offset=0;char permissions[5],file[4096];
        if(sscanf(line,"%" SCNxPTR "-%" SCNxPTR " %4s %lx %*s %*s %4095s",
            &start,&end,permissions,&offset,file)==5 && !offset && path==file){base=start;break;}
    }
    fclose(maps);return base;
}
std::string properties(const std::string &model,const std::string &fingerprint) {
    std::ostringstream out;out<<"[";bool comma=false;
    std::vector<std::string> paths;
    FILE *maps=fopen("/proc/self/maps","r");
    if(maps) {
        char line[8192],path[4096],permissions[5];uintptr_t start,end;unsigned long offset;
        while(fgets(line,sizeof(line),maps))if(sscanf(line,"%" SCNxPTR "-%" SCNxPTR " %4s %lx %*s %*s %4095s",
                &start,&end,permissions,&offset,path)==5 && !offset && !strncmp(path,"/dev/__properties__/",20))
            paths.emplace_back(path);
        fclose(maps);
    }
    for(const auto &path:paths) {
        int fd=open(path.c_str(),O_RDONLY|O_CLOEXEC);
        struct stat st{};
        if(fd<0)continue;
        if(fstat(fd,&st) || !S_ISREG(st.st_mode) || st.st_size<240 || st.st_size>16*1024*1024){close(fd);continue;}
        std::vector<uint8_t> bytes(st.st_size);
        ssize_t n=pread64(fd,bytes.data(),bytes.size(),0);
        if(n!=static_cast<ssize_t>(bytes.size())){close(fd);continue;}
        uint32_t magic=0;memcpy(&magic,bytes.data()+8,4);
        if(magic!=0x504f5250){close(fd);continue;}
        for(const auto &wanted:std::vector<std::pair<std::string,std::string>>{
                {"ro.product.model",model},{"ro.build.fingerprint",fingerprint}}) {
            size_t info=0;auto value=rawValue(bytes.data(),bytes.size(),wanted.first,&info);
            if(value.empty())continue;
            int cached=-1;
            for(auto &entry:cachedFiles)if(entry.first==path)cached=entry.second;
            if(cached<0){cached=dup(fd);cachedFiles.emplace_back(path,cached);}
            std::vector<uint8_t> cachedBytes(bytes.size());
            bool cachedRead=cached>=0 && raw(__NR_pread64,cached,reinterpret_cast<long>(cachedBytes.data()),
                cachedBytes.size(),0)==static_cast<long>(cachedBytes.size()) &&
                rawValue(cachedBytes.data(),cachedBytes.size(),wanted.first)==wanted.second;
            auto *mapped=static_cast<uint8_t *>(mmap(nullptr,bytes.size(),PROT_READ,MAP_SHARED,fd,0));
            bool mappedOkay=mapped!=MAP_FAILED && rawValue(mapped,bytes.size(),wanted.first)==wanted.second;
            if(mapped!=MAP_FAILED)munmap(mapped,bytes.size());
            int direct=static_cast<int>(raw(__NR_openat,AT_FDCWD,reinterpret_cast<long>(path.c_str()),O_RDONLY|O_CLOEXEC));
            std::vector<uint8_t> directBytes(bytes.size());
            bool directRead=direct>=0 && raw(__NR_pread64,direct,reinterpret_cast<long>(directBytes.data()),directBytes.size(),0)==
                static_cast<long>(directBytes.size()) && rawValue(directBytes.data(),directBytes.size(),wanted.first)==wanted.second;
            bool directMap=false;
            bool cachedMap=false;
#if defined(__aarch64__)
            auto *dm=reinterpret_cast<uint8_t *>(raw(__NR_mmap,0,bytes.size(),PROT_READ,MAP_SHARED,direct,0));
            directMap=dm!=MAP_FAILED && reinterpret_cast<uintptr_t>(dm)>4096 &&
                rawValue(dm,bytes.size(),wanted.first)==wanted.second;
            if(dm!=MAP_FAILED && reinterpret_cast<uintptr_t>(dm)>4096)munmap(dm,bytes.size());
            auto *cm=reinterpret_cast<uint8_t *>(raw(__NR_mmap,0,bytes.size(),PROT_READ,MAP_SHARED,cached,0));
            cachedMap=cm!=MAP_FAILED && reinterpret_cast<uintptr_t>(cm)>4096 &&
                rawValue(cm,bytes.size(),wanted.first)==wanted.second;
            if(cm!=MAP_FAILED && reinterpret_cast<uintptr_t>(cm)>4096)munmap(cm,bytes.size());
#endif
            if(direct>=0)close(direct);
            uintptr_t base=originalBase(path);
            bool original=base && rawValue(reinterpret_cast<uint8_t *>(base),bytes.size(),wanted.first)==wanted.second;
            if(comma)out<<",";comma=true;
            out<<"{\"name\":\""<<wanted.first<<"\",\"libcRead\":"<<(value==wanted.second?"true":"false")
                <<",\"libcMmap\":"<<(mappedOkay?"true":"false")<<",\"inlineRead\":"<<(directRead?"true":"false")
                <<",\"inlineMmap\":"<<(directMap?"true":"false")<<",\"cachedAreaSubstituted\":"<<(original?"true":"false")
                <<",\"cachedFdInlineRead\":"<<(cachedRead?"true":"false")
                <<",\"cachedFdInlineMmap\":"<<(cachedMap?"true":"false")
                <<",\"infoOffset\":"<<info<<"}";
        }
        close(fd);
    }
    out<<"]";return out.str();
}
std::string code() {
    void *entry=dlsym(RTLD_DEFAULT,"__system_property_find");Dl_info info{};
    if(!entry || !dladdr(entry,&info))return "{\"available\":false}";
    auto *header=static_cast<ElfW(Ehdr) *>(info.dli_fbase);
    auto *ph=reinterpret_cast<ElfW(Phdr) *>(static_cast<uint8_t *>(info.dli_fbase)+header->e_phoff);
    uintptr_t virtualAddress=reinterpret_cast<uintptr_t>(entry)-reinterpret_cast<uintptr_t>(info.dli_fbase);
    off64_t offset=-1;
    for(size_t i=0;i<header->e_phnum;++i)if(ph[i].p_type==PT_LOAD && virtualAddress>=ph[i].p_vaddr &&
        virtualAddress+64<=ph[i].p_vaddr+ph[i].p_filesz)offset=ph[i].p_offset+virtualAddress-ph[i].p_vaddr;
    uint8_t disk[64]{},api[64]{},direct[64]{};
    int file=open(info.dli_fname,O_RDONLY|O_CLOEXEC),memory=open("/proc/self/mem",O_RDONLY|O_CLOEXEC);
    bool available=file>=0 && memory>=0 && offset>=0 && pread64(file,disk,64,offset)==64;
    bool apiOkay=available && pread64(memory,api,64,reinterpret_cast<uintptr_t>(entry))==64 && !memcmp(api,disk,64);
    bool directOkay=available && raw(__NR_pread64,memory,reinterpret_cast<long>(direct),64,
        reinterpret_cast<long>(entry))==64 && !memcmp(direct,disk,64);
    bool actualDiffers=available && memcmp(entry,disk,64)!=0;
    if(file>=0)close(file);if(memory>=0)close(memory);
    std::ostringstream out;out<<"{\"available\":"<<(available?"true":"false")
        <<",\"apiMatchesDisk\":"<<(apiOkay?"true":"false")<<",\"inlineMatchesDisk\":"<<(directOkay?"true":"false")
        <<",\"executableRemainsHooked\":"<<(actualDiffers?"true":"false")<<"}";return out.str();
}
}
extern "C" JNIEXPORT jstring JNICALL
Java_io_github_lwtdzh_screenshotdetector_IncrementalProbeActivity_nativeProbe(JNIEnv *env,jclass,jstring model,jstring fingerprint,jstring path) {
    const char *m=env->GetStringUTFChars(model,nullptr),*f=env->GetStringUTFChars(fingerprint,nullptr);
    const char *p=env->GetStringUTFChars(path,nullptr);
    std::string output="{\"properties\":"+properties(m,f)+",\"code\":"+code()+",\"ordinary\":"+ordinary(p)+"}";
    env->ReleaseStringUTFChars(model,m);env->ReleaseStringUTFChars(fingerprint,f);
    env->ReleaseStringUTFChars(path,p);
    return env->NewStringUTF(output.c_str());
}
extern "C" JNIEXPORT jstring JNICALL
Java_io_github_lwtdzh_screenshotdetector_IncrementalProbeActivity_nativeEdges(JNIEnv *env,jclass,jstring model) {
    const char *wanted=env->GetStringUTFChars(model,nullptr);
    std::string path;size_t size=0;
    FILE *maps=fopen("/proc/self/maps","r");
    if(maps) {
        char line[8192],name[4096],permissions[5];uintptr_t start,end;unsigned long offset;
        while(fgets(line,sizeof(line),maps))
            if(sscanf(line,"%" SCNxPTR "-%" SCNxPTR " %4s %lx %*s %*s %4095s",
                &start,&end,permissions,&offset,name)==5 && !offset && !strncmp(name,"/dev/__properties__/",20)) {
                int fd=open(name,O_RDONLY|O_CLOEXEC);struct stat st{};
                if(fd>=0 && !fstat(fd,&st) && st.st_size>=240 && st.st_size<=16*1024*1024) {
                    std::vector<uint8_t> bytes(st.st_size);
                    if(pread64(fd,bytes.data(),bytes.size(),0)==static_cast<long>(bytes.size()) &&
                        !rawValue(bytes.data(),bytes.size(),"ro.product.model").empty()) {
                        path=name;size=bytes.size();close(fd);break;
                    }
                }
                if(fd>=0)close(fd);
            }
        fclose(maps);
    }
    int fd=path.empty()?-1:open(path.c_str(),O_RDONLY|O_CLOEXEC);
    std::vector<uint8_t> bytes(size);
    iovec parts[2]{{bytes.data(),size/3},{bytes.data()+size/3,size-size/3}};
    auto matches=[&](){return rawValue(bytes.data(),bytes.size(),"ro.product.model")==wanted;};
    bool readv=false,preadv=false,current=false,position=false,independent=false;
    bool badBuffer=false,pathOnly=false,writeMap=false,tooMany=false,eof=false;
    if(fd>=0) {
        lseek64(fd,0,SEEK_SET);
        readv=raw(__NR_readv,fd,reinterpret_cast<long>(parts),2)==static_cast<long>(size) && matches();
#ifdef __NR_preadv2
        lseek64(fd,19,SEEK_SET);
        preadv=raw(__NR_preadv2,fd,reinterpret_cast<long>(parts),2,0,0,0)==static_cast<long>(size) && matches();
        position=lseek64(fd,0,SEEK_CUR)==19;
        lseek64(fd,0,SEEK_SET);
        current=raw(__NR_preadv2,fd,reinterpret_cast<long>(parts),2,-1,0,0)==static_cast<long>(size) && matches()
            && lseek64(fd,0,SEEK_CUR)==static_cast<long>(size);
#endif
        int second=open(path.c_str(),O_RDONLY|O_CLOEXEC);
        independent=second>=0 && lseek64(second,0,SEEK_CUR)==0;
        if(second>=0)close(second);
        lseek64(fd,0,SEEK_SET);
        badBuffer=raw(__NR_read,fd,1,16)==-EFAULT && lseek64(fd,0,SEEK_CUR)==0;
        tooMany=raw(__NR_readv,fd,reinterpret_cast<long>(parts),1025)==-EINVAL;
        lseek64(fd,static_cast<off64_t>(size),SEEK_SET);
        eof=raw(__NR_readv,fd,reinterpret_cast<long>(parts),2)==0;
        int metadata=open(path.c_str(),O_PATH|O_CLOEXEC);
        pathOnly=metadata>=0 && raw(__NR_read,metadata,reinterpret_cast<long>(bytes.data()),1)==-EBADF;
        if(metadata>=0)close(metadata);
#if defined(__aarch64__)
        long map=raw(__NR_mmap,0,size,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);
        writeMap=map==-EACCES;
        if(map>0)munmap(reinterpret_cast<void *>(map),size);
#endif
        close(fd);
    }
    env->ReleaseStringUTFChars(model,wanted);
    std::ostringstream out;
    out<<"{\"rawReadvSelected\":"<<(readv?"true":"false")
        <<",\"rawPreadv2Selected\":"<<(preadv?"true":"false")
        <<",\"rawPreadv2CurrentOffset\":"<<(current?"true":"false")
        <<",\"preadvKeepsPosition\":"<<(position?"true":"false")
        <<",\"independentOpenPosition\":"<<(independent?"true":"false")
        <<",\"invalidBufferPreservesErrorAndOffset\":"<<(badBuffer?"true":"false")
        <<",\"oPathReadError\":"<<(pathOnly?"true":"false")
        <<",\"writeSharedMapDenied\":"<<(writeMap?"true":"false")
        <<",\"iovLimitError\":"<<(tooMany?"true":"false")
        <<",\"vectorEOF\":"<<(eof?"true":"false")<<"}";
    return env->NewStringUTF(out.str().c_str());
}
