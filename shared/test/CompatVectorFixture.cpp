#include <cstddef>
extern "C" __attribute__((visibility("default"), noinline))
int DobbyHook(void *, void *, void **) { return -1; }
extern "C" __attribute__((visibility("default"), noinline))
long vectorReplacement() { return 91; }
