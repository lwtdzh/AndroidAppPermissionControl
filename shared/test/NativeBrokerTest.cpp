#include <algorithm>
#include <atomic>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <signal.h>
#include <vector>
#include <unistd.h>
#include "../../app/src/main/cpp/device-raw-io.h"
#include "../../app/src/main/cpp/device-syscall-view.h"

namespace {
std::atomic<bool> enabled{true};
std::atomic<unsigned> views{0}, libcCopies{0};
std::atomic<pid_t> brokerTid{0};
volatile sig_atomic_t backtraces=0;
struct stat fixture{};
void backtrace(int) { ++backtraces; }

void require(bool condition, const char *message) {
    if (!condition) {
        fprintf(stderr, "FAIL %s errno=%d\n", message, errno);
        _exit(1);
    }
}
int opened(int fd) {
    brokerTid.store(gettid());
    struct stat st{};
    if (fd >= 0 && !device_io::stat(fd, &st) &&
        st.st_dev == fixture.st_dev && st.st_ino == fixture.st_ino) return fd;
    if (fd >= 0) device_io::close(fd);
    return -1;
}
void view(int, void *out, ssize_t count, off64_t) {
    if (count > 0) memset(out, 'Q', count);
    ++views;
}
void *worker(void *cookie) {
    int fd = *static_cast<int *>(cookie);
    char bytes[8]{};
    require(device_syscalls::sameProcess(gettid()), "live worker membership");
    require(pread(fd, bytes, 4, 0) == 4 && !memcmp(bytes, "QQQQ", 4),
            "worker selected read");
    return nullptr;
}
}

// A descriptor copy must bypass public hooks; these hooks may allocate or
// resolve libraries. The sentinel also catches accidental vector-path use.
extern "C" ssize_t process_vm_readv(pid_t, const iovec *, unsigned long,
                                    const iovec *, unsigned long, unsigned long) {
    ++libcCopies;
    errno = EIO;
    return -1;
}

int main() {
    struct sigaction action{};
    action.sa_handler=backtrace;
    sigemptyset(&action.sa_mask);
    require(!sigaction(33,&action,nullptr), "install reserved backtrace fixture");
    require(!syscall(__NR_tgkill,getpid(),gettid(),33) && backtraces==1,
            "ordinary caller receives backtrace signal");
    char name[] = "/data/local/tmp/appstate-broker-fixture-XXXXXX";
    int fd = mkstemp(name);
    require(fd >= 0, "create own fixture");
    unlink(name);
    require(write(fd, "abcdefgh", 8) == 8 && !fstat(fd, &fixture), "write own fixture");
    int copy = dup(fd);
    require(copy >= 0, "duplicate own fixture");
    iovec descriptor{nullptr, 17}, copied{};
    require(device_syscalls::copy(&descriptor, &copied, sizeof(copied)) &&
            copied.iov_len == 17 && !libcCopies, "raw descriptor copy");
    require(!device_syscalls::copy(reinterpret_cast<void *>(1), &copied, sizeof(copied)),
            "invalid descriptor copy");
    require(device_syscalls::start(opened, view, [] { return enabled.load(); }),
            "synchronized broker start");

    char a[4]{}, b[4]{};
    iovec vectors[]{{a, sizeof(a)}, {b, sizeof(b)}};
    require(lseek(fd, 0, SEEK_SET) == 0 && readv(fd, vectors, 2) == 8 &&
            !memcmp(a, "QQQQ", 4) && !memcmp(b, "QQQQ", 4), "selected readv");
    require(lseek(copy, 0, SEEK_CUR) == 8 && read(fd, a, sizeof(a)) == 0,
            "dup position and EOF");
    require(brokerTid.load()>0 && !syscall(__NR_tgkill,getpid(),brokerTid.load(),33),
            "send native backtrace to broker");
    require(pread(fd,a,sizeof(a),0)==4 && !memcmp(a,"QQQQ",4) && backtraces==1,
            "broker remains serving during native backtrace");
    require(!syscall(__NR_tgkill,getpid(),gettid(),33) && backtraces==2,
            "broker mask leaves caller backtrace signal unchanged");
    require(preadv(fd, vectors, 2, 0) == 8 && !memcmp(b, "QQQQ", 4),
            "selected preadv");
    require(!libcCopies, "broker vector copy bypasses public hooks");
    errno = 0;
    require(read(-1, a, sizeof(a)) == -1 && errno == EBADF, "ordinary invalid FD");
    int pipefd[2]{};
    require(!pipe(pipefd) && write(pipefd[1], "normal", 6) == 6 &&
            read(pipefd[0], a, 4) == 4 && !memcmp(a, "norm", 4), "ordinary pipe read");
    require(dup2(fd,pipefd[0])==pipefd[0] &&
            pread(pipefd[0],a,4,0)==4 && !memcmp(a,"QQQQ",4),
            "reused ordinary descriptor becomes selected");
    close(pipefd[0]); close(pipefd[1]);

    pthread_t thread;
    require(!pthread_create(&thread, nullptr, worker, &fd), "start worker");
    pthread_join(thread, nullptr);
    pid_t child = fork();
    require(child >= 0, "fork child");
    if (!child) {
        // Its inherited filter is served by the parent; membership must cause
        // CONTINUE, preserving the child's genuine bytes.
        require(pread(fd, a, sizeof(a), 0) == 4 && !memcmp(a, "abcd", 4),
                "child genuine bytes");
        _exit(0);
    }
    int status = 0;
    require(waitpid(child, &status, 0) == child && WIFEXITED(status) &&
            WEXITSTATUS(status) == 0, "child ownership isolation");
    enabled = false;
    require(pread(fd, a, sizeof(a), 0) == 4 && !memcmp(a, "abcd", 4),
            "disable restores original bytes");
    close(copy); close(fd);
    printf("PASS raw descriptor copies, readv/preadv, worker/child isolation, "
           "dup/EOF/EBADF, ordinary pipe, broker backtrace isolation and disable; views=%u\n", views.load());
    return 0;
}
