#include <asm/unistd.h>

#if defined(__aarch64__)
.text
.global probe_clone_new_stack
.hidden probe_clone_new_stack
.type probe_clone_new_stack, %function
// x0: top of an empty child stack. The child exits before touching the parent's
// frame. A C++ syscall hook that unwinds on the child stack fails this control.
probe_clone_new_stack:
    bti c
    stp x29, x30, [sp, #-16]!
    mov x29, sp
    mov x2, x0
    mov x0, __NR_clone
    mov x1, 17 // SIGCHLD, no CLONE_VM: isolated test child
    mov x3, xzr
    mov x4, xzr
    mov x5, xzr
    mov x6, xzr
    bl syscall
    cbz x0, .Lchild
    ldp x29, x30, [sp], #16
    ret
.Lchild:
    mov x0, xzr
    mov x8, __NR_exit
    svc #0
    brk #0
.size probe_clone_new_stack, .-probe_clone_new_stack
#elif defined(__x86_64__)
.text
.global probe_clone_new_stack
.hidden probe_clone_new_stack
.type probe_clone_new_stack, %function
probe_clone_new_stack:
    push %rbp
    mov %rsp, %rbp
    mov %rdi, %rdx
    mov $__NR_clone, %edi
    mov $17, %esi
    xor %ecx, %ecx
    xor %r8d, %r8d
    xor %r9d, %r9d
    xor %eax, %eax
    sub $16, %rsp
    movq $0, (%rsp)
    call syscall
    test %rax, %rax
    je .Lchild
    leave
    ret
.Lchild:
    xor %edi, %edi
    mov $__NR_exit, %eax
    syscall
    ud2
.size probe_clone_new_stack, .-probe_clone_new_stack
#endif
.section .note.GNU-stack,"",%progbits
