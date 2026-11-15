#include <jni.h>
#include <sys/system_properties.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <linux/capability.h>
#include <linux/audit.h>
#include <sched.h>
#include <poll.h>
#include <unistd.h>
#include <signal.h>
#include <cerrno>
#include <cstddef>
#include <cstring>
#include <vector>
#include <string>
#include <sstream>

namespace {
constexpr char LONG_MESSAGE[]="Must use __system_property_read_callback() to read";
#if defined(__aarch64__)
constexpr unsigned ARCH=AUDIT_ARCH_AARCH64;
long rawGetpid(){register long x8 asm("x8")=__NR_getpid;register long x0 asm("x0");asm volatile("svc #0":"=r"(x0):"r"(x8):"memory","cc");return x0;}
#elif defined(__arm__)
constexpr unsigned ARCH=AUDIT_ARCH_ARM;
__attribute__((naked)) long rawGetpid(){asm volatile("push {r7, lr}\nmovs r7, #20\nsvc #0\npop {r7, pc}");}
#elif defined(__x86_64__)
constexpr unsigned ARCH=AUDIT_ARCH_X86_64;
long rawGetpid(){long result;asm volatile("syscall":"=a"(result):"a"(__NR_getpid):"rcx","r11","memory");return result;}
#else
constexpr unsigned ARCH=AUDIT_ARCH_I386;
long rawGetpid(){long result;asm volatile("int $0x80":"=a"(result):"a"(__NR_getpid):"memory","cc");return result;}
#endif
struct KernelResult{
    int uid=-1,seccomp=-1,noNewPrivs=-1,noNewPrivsError=0;
    int unshareResult=-2,unshareError=0,filterResult=-2,filterError=0;
    int listenerResult=-2,listenerError=0,trapFilterResult=-2,trapFilterError=0;
    long rawPidBefore=-1,rawPidAfter=-1;
    unsigned long long effectiveCaps=0;
};
KernelResult inChild(){
    KernelResult out;out.uid=getuid();out.seccomp=prctl(PR_GET_SECCOMP,0,0,0,0);out.rawPidBefore=rawGetpid();
    __user_cap_header_struct header{_LINUX_CAPABILITY_VERSION_3,0};__user_cap_data_struct caps[2]{};
    if(syscall(__NR_capget,&header,caps)==0)out.effectiveCaps=(static_cast<unsigned long long>(caps[1].effective)<<32)|caps[0].effective;
    errno=0;out.unshareResult=unshare(CLONE_NEWNS);out.unshareError=errno;
    errno=0;out.noNewPrivs=prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0);out.noNewPrivsError=errno;
    sock_filter allow[]={BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ALLOW)};
    sock_fprog allowProgram{1,allow};
    errno=0;out.filterResult=syscall(__NR_seccomp,SECCOMP_SET_MODE_FILTER,0,&allowProgram);out.filterError=errno;
    errno=0;out.listenerResult=syscall(__NR_seccomp,SECCOMP_SET_MODE_FILTER,SECCOMP_FILTER_FLAG_NEW_LISTENER,&allowProgram);
    out.listenerError=errno;if(out.listenerResult>=0)close(out.listenerResult);
    sock_filter filter[]={
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS,offsetof(seccomp_data,arch)),
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,ARCH,1,0),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ALLOW),
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS,offsetof(seccomp_data,nr)),
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,__NR_getpid,0,1),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ERRNO|EACCES),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ALLOW)};
    sock_fprog program{static_cast<unsigned short>(sizeof(filter)/sizeof(filter[0])),filter};
    errno=0;out.trapFilterResult=syscall(__NR_seccomp,SECCOMP_SET_MODE_FILTER,0,&program);out.trapFilterError=errno;
    out.rawPidAfter=rawGetpid();
    return out;
}
struct PropertyValue{std::string name,value;unsigned serial=0;};
void readCallback(void* cookie,const char* name,const char* value,uint32_t serial){
    auto& out=*static_cast<PropertyValue*>(cookie);out.name=name;out.value=value;out.serial=serial;
}
std::string propertyPrototype(){
    std::ostringstream json;json<<"[";bool comma=false;
    for(unsigned length:{48u,91u,128u,256u}){
        const std::string name="ro.appstate.research.fingerprint";
        const std::string value(length,'S');
        bool longValue=length>=PROP_VALUE_MAX;
        unsigned offset=96+static_cast<unsigned>(name.size())+1;
        offset=(offset+3)&~3u;
        std::vector<uint32_t> words((offset+value.size()+4)/4,0);
        auto* bytes=reinterpret_cast<char*>(words.data());
        const char* legacy=longValue?LONG_MESSAGE:value.c_str();
        unsigned serial=(static_cast<unsigned>(strlen(legacy))<<24)|(longValue?(1u<<16):0u);
        __atomic_store_n(words.data(),serial,__ATOMIC_RELAXED);
        memcpy(bytes+4,legacy,strlen(legacy)+1);
        if(longValue){memcpy(bytes+60,&offset,sizeof(offset));memcpy(bytes+offset,value.c_str(),value.size()+1);}
        memcpy(bytes+96,name.c_str(),name.size()+1);
        const auto* pi=reinterpret_cast<const prop_info*>(bytes);
        PropertyValue callback;__system_property_read_callback(pi,readCallback,&callback);
        struct Guard{unsigned char before[16];char value[PROP_VALUE_MAX];unsigned char after[16];} slot;
        memset(&slot,0xa5,sizeof(slot));memset(slot.value,0,sizeof(slot.value));
        int count=__system_property_read(pi,nullptr,slot.value);
        bool safe=true;for(auto c:slot.before)safe&=c==0xa5;for(auto c:slot.after)safe&=c==0xa5;
        uint32_t publicSerial=__system_property_serial(pi),updated=0xabcdef12;
        timespec timeout{0,0};bool woke=__system_property_wait(pi,publicSerial,&updated,&timeout);
        bool okay=callback.name==name&&callback.value==value&&callback.serial==serial&&publicSerial==serial&&
            slot.value==std::string(legacy)&&count==static_cast<int>(strlen(legacy))&&safe&&!woke&&updated==0xabcdef12;
        if(comma)json<<",";comma=true;
        json<<"{\"length\":"<<length<<",\"passed\":"<<(okay?"true":"false")
            <<",\"serialLength\":"<<(publicSerial>>24)<<",\"longFlag\":"<<((publicSerial&(1u<<16))?"true":"false")
            <<",\"callbackReadsSyntheticValue\":"<<((callback.value==value)?"true":"false")
            <<",\"bufferGuards\":"<<(safe?"true":"false")<<",\"zeroTimeoutReturnsFalse\":"<<(!woke?"true":"false")<<"}";
    }
    json<<"]";return json.str();
}
}
extern "C" JNIEXPORT jstring JNICALL
Java_io_github_lwtdzh_screenshotdetector_CapabilityProbeActivity_nativeProbe(JNIEnv* env,jclass){
    const int parentMode=prctl(PR_GET_SECCOMP,0,0,0,0),parentNnp=prctl(PR_GET_NO_NEW_PRIVS,0,0,0,0);
    std::string properties=propertyPrototype();
    KernelResult result;int pipefd[2],status=0;bool received=false;pid_t child=-1;
    if(pipe(pipefd)==0){
        child=fork();
        if(child==0){
            close(pipefd[0]);KernelResult local=inChild();write(pipefd[1],&local,sizeof(local));close(pipefd[1]);_exit(0);
        }
        close(pipefd[1]);
        if(child>0){
            pollfd pending{pipefd[0],POLLIN,0};
            if(poll(&pending,1,3000)>0)received=read(pipefd[0],&result,sizeof(result))==sizeof(result);
            if(!received)kill(child,SIGKILL);
            waitpid(child,&status,0);
        }
        close(pipefd[0]);
    }
    std::ostringstream out;
    out<<"{\"syntheticProperties\":"<<properties<<",\"childReceived\":"<<(received?"true":"false")
       <<",\"childStatus\":"<<status<<",\"childUid\":"<<result.uid<<",\"effectiveCaps\":"<<result.effectiveCaps
       <<",\"inheritedSeccomp\":"<<result.seccomp<<",\"noNewPrivsResult\":"<<result.noNewPrivs
       <<",\"noNewPrivsErrno\":"<<result.noNewPrivsError<<",\"unshareResult\":"<<result.unshareResult
       <<",\"unshareErrno\":"<<result.unshareError<<",\"allowFilterResult\":"<<result.filterResult
       <<",\"allowFilterErrno\":"<<result.filterError<<",\"listenerResult\":"<<result.listenerResult
       <<",\"listenerErrno\":"<<result.listenerError<<",\"errnoFilterResult\":"<<result.trapFilterResult
       <<",\"errnoFilterErrno\":"<<result.trapFilterError<<",\"rawGetpidBefore\":"<<result.rawPidBefore
       <<",\"rawGetpidAfter\":"<<result.rawPidAfter<<",\"parentSeccompUnchanged\":"
       <<((parentMode==prctl(PR_GET_SECCOMP,0,0,0,0))?"true":"false")<<",\"parentNoNewPrivsUnchanged\":"
       <<((parentNnp==prctl(PR_GET_NO_NEW_PRIVS,0,0,0,0))?"true":"false")<<"}";
    return env->NewStringUTF(out.str().c_str());
}
