#include <asm/unistd.h>
// 仅自身代码读取进入 C++；clone 等调用原样跳转，保留栈和六个参数。
.text
.global compat_syscall_dispatch
.hidden compat_syscall_dispatch
.hidden compat_original_syscall
.hidden compat_filtered_syscall
.type compat_syscall_dispatch, %function
compat_syscall_dispatch:
#if defined(__aarch64__)
    bti c
    cmp x0, __NR_process_vm_readv
    b.eq compat_filtered_syscall
    adrp x16, compat_original_syscall
    ldr x16, [x16, :lo12:compat_original_syscall]
    br x16
#elif defined(__arm__)
    .arm
    movw ip, __NR_process_vm_readv
    cmp r0, ip
    beq compat_filtered_syscall
    ldr ip, .Lcompat_offset
.Lcompat_pc:
    add ip, pc, ip
    ldr ip, [ip]
    bx ip
    .align 2
.Lcompat_offset:
    .word compat_original_syscall - (.Lcompat_pc + 8)
#elif defined(__x86_64__)
    cmpq $__NR_process_vm_readv, %rdi
    je compat_filtered_syscall
    jmp *compat_original_syscall(%rip)
#elif defined(__i386__)
    cmpl $__NR_process_vm_readv, 4(%esp)
    je compat_filtered_syscall
    call .Lcompat_pc
.Lcompat_pc:
    pop %eax
    mov compat_original_syscall-.Lcompat_pc(%eax), %eax
    jmp *%eax
#endif
.size compat_syscall_dispatch, .-compat_syscall_dispatch
.section .note.GNU-stack,"",%progbits
