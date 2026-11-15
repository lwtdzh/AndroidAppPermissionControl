#pragma once
#include <linux/audit.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <sys/ioctl.h>
#include <sys/prctl.h>
#include <sys/uio.h>
#include <pthread.h>
#include <atomic>
#include <cstddef>
#include <poll.h>
#include <sys/eventfd.h>

#ifndef SECCOMP_FILTER_FLAG_TSYNC_ESRCH
#define SECCOMP_FILTER_FLAG_TSYNC_ESRCH (1UL << 4)
#endif
namespace device_syscalls {
using OpenView=int (*)(int);
using ReadView=void (*)(int,void *,ssize_t,off64_t);
using Active=bool (*)();
inline std::atomic<int> listener{-1}, state{0}, setupErrno{0};
inline OpenView opened=nullptr;
inline ReadView readView=nullptr;
inline Active active=nullptr;
inline bool copy(const void *source,void *out,size_t n) {
    iovec local{out,n},remote{const_cast<void *>(source),n};
    return process_vm_readv(getpid(),&local,1,&remote,1,0)==static_cast<ssize_t>(n);
}
inline bool sameProcess(pid_t tid) {
    if(tid==getpid())return true;
    char path[64],bytes[4096];
    snprintf(path,sizeof(path),"/proc/%d/status",tid);
    int fd=device_io::open(path,O_RDONLY|O_CLOEXEC);
    if(fd<0)return false;
    ssize_t n=device_io::call(__NR_read,fd,reinterpret_cast<long>(bytes),sizeof(bytes)-1);
    device_io::close(fd);if(n<=0)return false;bytes[n]=0;
    const char *p=strstr(bytes,"Tgid:");
    return p && strtol(p+5,nullptr,10)==getpid();
}
inline void vectorView(int fd,const iovec *source,int count,ssize_t result,off64_t start) {
    if(count<=0 || count>1024 || result<=0)return;
    iovec iov[1024];
    if(!copy(source,iov,count*sizeof(iovec)))return;
    size_t remaining=result;
    for(int i=0;i<count;++i) {
        size_t n=std::min(remaining,iov[i].iov_len);
        if(n)readView(fd,iov[i].iov_base,n,start);
        remaining-=n;start+=n;if(!remaining)break;
    }
}
inline void *serve(void *) {
    int fd=listener.load();if(fd<0)return nullptr;
    seccomp_notif request{};
    while(true) {
        memset(&request,0,sizeof(request));
        if(ioctl(fd,SECCOMP_IOCTL_NOTIF_RECV,&request)) {
            if(errno==EINTR || errno==ENOENT)continue;
            state.store(-4);break;
        }
        seccomp_notif_resp response{};
        response.id=request.id;response.flags=SECCOMP_USER_NOTIF_FLAG_CONTINUE;
        auto &a=request.data.args;int number=request.data.nr;
        if(active() && !ioctl(fd,SECCOMP_IOCTL_NOTIF_ID_VALID,&request.id) && sameProcess(request.pid)) {
            uint64_t call[6];memcpy(call,a,sizeof(call));
            uint32_t oldMap[6]{};
#if defined(__i386__)
            // i386's original mmap takes a pointer to six 32-bit words.
            // Decode a local copy and never mutate the caller's argument block.
            if(number==__NR_mmap) {
                if(!copy(reinterpret_cast<void *>(a[0]),oldMap,sizeof(oldMap))) {
                    response.flags=0;response.error=-EFAULT;
                    ioctl(fd,SECCOMP_IOCTL_NOTIF_SEND,&response);continue;
                }
                for(size_t i=0;i<6;++i)call[i]=oldMap[i];
            }
#endif
            bool mapping=false;
#ifdef __NR_mmap
            mapping=number==__NR_mmap;
#endif
#ifdef __NR_mmap2
            mapping=mapping || number==__NR_mmap2;
#endif
            int target=mapping?static_cast<int>(call[4]):static_cast<int>(call[0]);
            // Probe callback performs only fstat/cache lookups, without heap
            // allocation or intercepted I/O. All unrelated calls CONTINUE.
            int shadow=opened(device_io::duplicate(target));
            bool selected=shadow>=0 && shadow!=target;
            // opened returns -1 for an unselected descriptor and closes its dup.
            if(selected) {
                if(mapping && !(call[2]&PROT_WRITE) && !(call[3]&MAP_ANONYMOUS)) {
                    call[4]=shadow;call[3]=(call[3]&~MAP_SHARED)|MAP_PRIVATE;
                }
#if defined(__i386__)
                if(number==__NR_mmap) {
                    for(size_t i=0;i<6;++i)oldMap[i]=static_cast<uint32_t>(call[i]);
                    call[0]=reinterpret_cast<uintptr_t>(oldMap);
                }
#endif
                long result=device_io::call(number,static_cast<unsigned long>(call[0]),
                    static_cast<unsigned long>(call[1]),static_cast<unsigned long>(call[2]),
                    static_cast<unsigned long>(call[3]),static_cast<unsigned long>(call[4]),
                    static_cast<unsigned long>(call[5]));
                int error=errno;
                if(result>0 && !mapping) {
                    off64_t offset=0;bool vector=number==__NR_readv;
#ifdef __NR_preadv
                    vector=vector || number==__NR_preadv;
#endif
#ifdef __NR_preadv2
                    vector=vector || number==__NR_preadv2;
#endif
                    if(number==__NR_read || number==__NR_readv)offset=device_io::seek(target,0,SEEK_CUR)-result;
                    else if(vector) {
#if defined(__arm__) || defined(__i386__)
                        offset=static_cast<off64_t>((a[3]&0xffffffffu)|((a[4]&0xffffffffu)<<32));
#else
                        offset=static_cast<off64_t>(a[3]);
#endif
#ifdef __NR_preadv2
                        // preadv2 offset -1 uses and advances the descriptor's
                        // current position; it is not a negative pread offset.
                        if(number==__NR_preadv2 && offset==-1)
                            offset=device_io::seek(target,0,SEEK_CUR)-result;
#endif
                    }
                    else {
#if defined(__arm__)
                        offset=static_cast<off64_t>((a[4]&0xffffffffu)|((a[5]&0xffffffffu)<<32));
#elif defined(__i386__)
                        offset=static_cast<off64_t>((a[3]&0xffffffffu)|((a[4]&0xffffffffu)<<32));
#else
                        offset=static_cast<off64_t>(a[3]);
#endif
                    }
                    if(vector)vectorView(target,reinterpret_cast<const iovec *>(a[1]),a[2],result,offset);
                    else readView(target,reinterpret_cast<void *>(a[1]),result,offset);
                }
                if(shadow>=0)device_io::close(shadow);
                response.flags=0;
                if(result==-1)response.error=-error;else response.val=result;
            }
        }
        if(ioctl(fd,SECCOMP_IOCTL_NOTIF_SEND,&response) && errno!=ENOENT && errno!=EINTR) {
            state.store(-5);break;
        }
    }
    return nullptr;
}
struct Start{int readEnd,readyEnd;};
inline void *awaitListener(void *raw) {
    auto argument=*static_cast<Start *>(raw);
    delete static_cast<Start *>(raw);
    int readEnd=argument.readEnd,value=-1;uint64_t ready=1;
    // pthread initialization may itself perform libc I/O. Do not synchronize
    // the filter until this thread has reached its raw, allocation-free loop.
    device_io::call(__NR_write,argument.readyEnd,reinterpret_cast<long>(&ready),sizeof(ready));
    device_io::close(argument.readyEnd);
    ssize_t n=device_io::call(__NR_read,readEnd,reinterpret_cast<long>(&value),sizeof(value));
    device_io::close(readEnd);
    if(n==sizeof(value) && value>=0)return serve(nullptr);
    return nullptr;
}
inline bool start(OpenView open,ReadView view,Active enabled) {
    if(state.load()!=0)return state.load()==1;
    opened=open;readView=view;active=enabled;
    int pipe[2];if(pipe2(pipe,O_CLOEXEC)){state.store(-1);return false;}
    int readyReader=eventfd(0,EFD_CLOEXEC|EFD_NONBLOCK);
    int readyWriter=readyReader>=0?dup(readyReader):-1;
    if(readyWriter<0){if(readyReader>=0)close(readyReader);close(pipe[0]);close(pipe[1]);state.store(-1);return false;}
    pthread_t broker;
    auto *argument=new Start{pipe[0],readyWriter};
    if(pthread_create(&broker,nullptr,awaitListener,argument)) {
        delete argument;close(readyReader);close(readyWriter);close(pipe[0]);close(pipe[1]);state.store(-2);return false;
    }
    pthread_detach(broker);
    pollfd readyFd{readyReader,POLLIN,0};uint64_t ready=0;
    if(poll(&readyFd,1,3000)!=1 || read(readyReader,&ready,sizeof(ready))!=sizeof(ready) || ready!=1) {
        int failure=-1;write(pipe[1],&failure,sizeof(failure));
        close(pipe[1]);close(readyReader);state.store(-6);return false;
    }
    close(readyReader);
    std::vector<sock_filter> code;
    auto stmt=[&](uint16_t op,uint32_t k){code.push_back(sock_filter{op,0,0,k});};
    auto jump=[&](uint16_t op,uint32_t k,uint8_t yes,uint8_t no){code.push_back(sock_filter{op,yes,no,k});};
    stmt(BPF_LD|BPF_W|BPF_ABS,offsetof(seccomp_data,arch));
#if defined(__aarch64__)
    constexpr uint32_t arch=AUDIT_ARCH_AARCH64;
#elif defined(__arm__)
    constexpr uint32_t arch=AUDIT_ARCH_ARM;
#elif defined(__x86_64__)
    constexpr uint32_t arch=AUDIT_ARCH_X86_64;
#else
    constexpr uint32_t arch=AUDIT_ARCH_I386;
#endif
    jump(BPF_JMP|BPF_JEQ|BPF_K,arch,1,0);stmt(BPF_RET|BPF_K,SECCOMP_RET_ALLOW);
    uintptr_t site=reinterpret_cast<uintptr_t>(&device_raw_return);
    stmt(BPF_LD|BPF_W|BPF_ABS,offsetof(seccomp_data,instruction_pointer)+4);
    jump(BPF_JMP|BPF_JEQ|BPF_K,static_cast<uint64_t>(site)>>32,0,3);
    stmt(BPF_LD|BPF_W|BPF_ABS,offsetof(seccomp_data,instruction_pointer));
    jump(BPF_JMP|BPF_JEQ|BPF_K,site,0,1);stmt(BPF_RET|BPF_K,SECCOMP_RET_ALLOW);
    stmt(BPF_LD|BPF_W|BPF_ABS,offsetof(seccomp_data,nr));
    for(int nr:{__NR_read,__NR_pread64,__NR_readv
#ifdef __NR_preadv
                ,__NR_preadv
#endif
#ifdef __NR_preadv2
                ,__NR_preadv2
#endif
#ifdef __NR_mmap
                ,__NR_mmap
#endif
#ifdef __NR_mmap2
                ,__NR_mmap2
#endif
    }) {jump(BPF_JMP|BPF_JEQ|BPF_K,nr,0,1);stmt(BPF_RET|BPF_K,SECCOMP_RET_USER_NOTIF);}
    stmt(BPF_RET|BPF_K,SECCOMP_RET_ALLOW);
    sock_fprog program{static_cast<unsigned short>(code.size()),code.data()};
    int fd=-1;
    if(!prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0))
        fd=static_cast<int>(syscall(__NR_seccomp,SECCOMP_SET_MODE_FILTER,
            SECCOMP_FILTER_FLAG_NEW_LISTENER|SECCOMP_FILTER_FLAG_TSYNC|SECCOMP_FILTER_FLAG_TSYNC_ESRCH,&program));
    setupErrno.store(fd<0?errno:0);listener.store(fd);state.store(fd>=0?1:-3);
    write(pipe[1],&fd,sizeof(fd));close(pipe[1]);return fd>=0;
}
}
