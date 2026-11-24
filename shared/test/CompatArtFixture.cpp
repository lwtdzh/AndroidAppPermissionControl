// 保留本地符号表，模拟 vivo ART 中只存在于 .symtab 的函数。
extern "C" long registerNativeFixture();
#if defined(__aarch64__)
asm(".text\n.align 4\n.hidden registerNativeFixture\n"
    ".type registerNativeFixture,%function\nregisterNativeFixture:\n"
    "mov x0,#42\nret\nnop\nnop\n.size registerNativeFixture,.-registerNativeFixture\n");
#endif
extern "C" __attribute__((visibility("default")))
void *fixtureEntry() { return reinterpret_cast<void *>(registerNativeFixture); }
