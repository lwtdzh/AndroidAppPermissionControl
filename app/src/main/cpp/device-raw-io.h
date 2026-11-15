#pragma once
#include <cerrno>
#include <cstdint>
#include <sys/syscall.h>
#include <unistd.h>

// One module-owned syscall instruction lets the synchronized broker perform
// its own I/O without notifying itself. No libc allocation or I/O in that path.
extern "C" __attribute__((visibility("hidden"))) long device_raw6(
    long,long,long,long,long,long,long);
extern "C" __attribute__((visibility("hidden"))) char device_raw_return;
#if defined(__aarch64__)
asm(".text\n.align 2\n.hidden device_raw6\n.type device_raw6,%function\n"
    "device_raw6:\nmov x8,x0\nmov x0,x1\nmov x1,x2\nmov x2,x3\n"
    "mov x3,x4\nmov x4,x5\nmov x5,x6\nsvc #0\n"
    ".hidden device_raw_return\ndevice_raw_return:\nret\n");
#elif defined(__arm__)
asm(".text\n.align 2\n.arm\n.hidden device_raw6\n.type device_raw6,%function\n"
    "device_raw6:\npush {r4,r5,r6,r7,lr}\nmov r7,r0\nmov r0,r1\nmov r1,r2\nmov r2,r3\n"
    "ldr r3,[sp,#20]\nldr r4,[sp,#24]\nldr r5,[sp,#28]\nsvc #0\n"
    ".hidden device_raw_return\ndevice_raw_return:\npop {r4,r5,r6,r7,pc}\n");
#elif defined(__x86_64__)
asm(".text\n.hidden device_raw6\n.type device_raw6,@function\n"
    "device_raw6:\nmov %rdi,%rax\nmov %rsi,%rdi\nmov %rdx,%rsi\nmov %rcx,%rdx\n"
    "mov %r8,%r10\nmov %r9,%r8\nmov 8(%rsp),%r9\nsyscall\n"
    ".hidden device_raw_return\ndevice_raw_return:\nret\n");
#else
asm(".text\n.hidden device_raw6\n.type device_raw6,@function\n"
    "device_raw6:\npush %ebx\npush %esi\npush %edi\npush %ebp\n"
    "mov 20(%esp),%eax\nmov 24(%esp),%ebx\nmov 28(%esp),%ecx\nmov 32(%esp),%edx\n"
    "mov 36(%esp),%esi\nmov 40(%esp),%edi\nmov 44(%esp),%ebp\nint $0x80\n"
    ".hidden device_raw_return\ndevice_raw_return:\npop %ebp\npop %edi\npop %esi\npop %ebx\nret\n");
#endif
namespace device_io {
inline long call(long n,long a=0,long b=0,long c=0,long d=0,long e=0,long f=0) {
    long out=device_raw6(n,a,b,c,d,e,f);
    if(static_cast<unsigned long>(out)>=static_cast<unsigned long>(-4095L)) {
        errno=static_cast<int>(-out);return -1;
    }
    return out;
}
inline int open(const char *name,int flags) {
    return static_cast<int>(call(__NR_openat,AT_FDCWD,reinterpret_cast<long>(name),flags));
}
inline int close(int fd){return call(__NR_close,fd);}
inline int fcntl(int fd,int operation,long argument=0) {
#ifdef __NR_fcntl64
    return call(__NR_fcntl64,fd,operation,argument);
#else
    return call(__NR_fcntl,fd,operation,argument);
#endif
}
inline int duplicate(int fd){return fcntl(fd,F_DUPFD_CLOEXEC,0);}
inline int stat(int fd,struct stat *out) {
#ifdef __NR_fstat64
    return call(__NR_fstat64,fd,reinterpret_cast<long>(out));
#else
    return call(__NR_fstat,fd,reinterpret_cast<long>(out));
#endif
}
inline ssize_t link(const char *path,char *out,size_t n) {
    return call(__NR_readlinkat,AT_FDCWD,reinterpret_cast<long>(path),reinterpret_cast<long>(out),n);
}
inline off64_t seek(int fd,off64_t offset,int origin) {
#ifdef __NR__llseek
    off64_t out=0;
    if(call(__NR__llseek,fd,static_cast<uint64_t>(offset)>>32,static_cast<uint32_t>(offset),
            reinterpret_cast<long>(&out),origin)<0)return -1;
    return out;
#else
    return call(__NR_lseek,fd,offset,origin);
#endif
}
inline ssize_t pread(int fd,void *data,size_t n,off64_t offset) {
#if defined(__arm__)
    return call(__NR_pread64,fd,reinterpret_cast<long>(data),n,0,
        static_cast<uint32_t>(offset),static_cast<uint64_t>(offset)>>32);
#elif defined(__i386__)
    return call(__NR_pread64,fd,reinterpret_cast<long>(data),n,
        static_cast<uint32_t>(offset),static_cast<uint64_t>(offset)>>32);
#else
    return call(__NR_pread64,fd,reinterpret_cast<long>(data),n,offset);
#endif
}
inline void *map(void *address,size_t n,int protection,int flags,int fd,off64_t offset) {
#ifdef __NR_mmap2
    return reinterpret_cast<void *>(call(__NR_mmap2,reinterpret_cast<long>(address),
        n,protection,flags,fd,offset/4096));
#else
    return reinterpret_cast<void *>(call(__NR_mmap,reinterpret_cast<long>(address),
        n,protection,flags,fd,offset));
#endif
}
}
