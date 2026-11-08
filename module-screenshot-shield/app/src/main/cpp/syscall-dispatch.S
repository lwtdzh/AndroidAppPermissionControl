#include <asm/unistd.h>

// Only filesystem observation and descriptor tracking need the C++ handler.
// All other calls retain the caller's stack and return address, including clone:
// its child returns on a new stack that contains none of our C++ saved registers.
.text
.global shield_syscall_dispatch
.hidden shield_syscall_dispatch
.hidden shield_original_syscall
.hidden shield_filtered_syscall
.type shield_syscall_dispatch, %function
shield_syscall_dispatch:
#if defined(__aarch64__)
    bti c
#define ROUTE(n) cmp x0, n; b.eq shield_filtered_syscall
#elif defined(__arm__)
    .arm
#define ROUTE(n) movw ip, n; cmp r0, ip; beq shield_filtered_syscall
#elif defined(__x86_64__)
#define ROUTE(n) cmpq $n, %rdi; je shield_filtered_syscall
#elif defined(__i386__)
#define ROUTE(n) cmpl $n, 4(%esp); je shield_filtered_syscall
#else
#error Unsupported Android ABI
#endif
    ROUTE(__NR_read)
    ROUTE(__NR_readv)
    ROUTE(__NR_pread64)
#ifdef __NR_preadv
    ROUTE(__NR_preadv)
#endif
#ifdef __NR_preadv2
    ROUTE(__NR_preadv2)
#endif
#ifdef __NR_fstat
    ROUTE(__NR_fstat)
#endif
#ifdef __NR_fstat64
    ROUTE(__NR_fstat64)
#endif
#ifdef __NR_mmap
    ROUTE(__NR_mmap)
#endif
#ifdef __NR_mmap2
    ROUTE(__NR_mmap2)
#endif
    ROUTE(__NR_openat)
    ROUTE(__NR_faccessat)
    ROUTE(__NR_inotify_add_watch)
#ifdef __NR_newfstatat
    ROUTE(__NR_newfstatat)
#endif
#ifdef __NR_statx
    ROUTE(__NR_statx)
#endif
    ROUTE(__NR_readlinkat)
#ifdef __NR_readlink
    ROUTE(__NR_readlink)
#endif
    ROUTE(__NR_getdents64)
    ROUTE(__NR_inotify_init1)
    ROUTE(__NR_close)
#ifdef __NR_dup
    ROUTE(__NR_dup)
#endif
#ifdef __NR_dup2
    ROUTE(__NR_dup2)
#endif
#ifdef __NR_dup3
    ROUTE(__NR_dup3)
#endif
#ifdef __NR_fcntl
    ROUTE(__NR_fcntl)
#endif
#ifdef __NR_fcntl64
    ROUTE(__NR_fcntl64)
#endif
#undef ROUTE
#if defined(__aarch64__)
    adrp x16, shield_original_syscall
    ldr x16, [x16, :lo12:shield_original_syscall]
    br x16
#elif defined(__arm__)
    ldr ip, .Loriginal_offset
.Loriginal_pc:
    add ip, pc, ip
    ldr ip, [ip]
    bx ip
    .align 2
.Loriginal_offset:
    .word shield_original_syscall - (.Loriginal_pc + 8)
#elif defined(__x86_64__)
    jmp *shield_original_syscall(%rip)
#elif defined(__i386__)
    call .Loriginal_pc
.Loriginal_pc:
    pop %eax
    mov shield_original_syscall-.Loriginal_pc(%eax), %eax
    jmp *%eax
#endif
.size shield_syscall_dispatch, .-shield_syscall_dispatch
.section .note.GNU-stack,"",%progbits
