#include "property-read.h"
#include <array>
#include <cassert>
#include <iostream>

struct prop_info { std::string name, value; };
static int checks;
static void check(bool ok) { assert(ok);++checks; }
static void original(const prop_info *info,shield_properties::Callback callback,void *cookie) {
    callback(cookie,info->name.c_str(),info->value.c_str(),0);
    errno=EINVAL;
}
int main() {
    const std::string compatibility="Must use __system_property_read_callback() to read";
    for(size_t length:{0,1,48,90,91,92,93,128,256})for(const char *key:{"ro.build.fingerprint","persist.test.value"}){
        std::array<unsigned char,124> memory;memory.fill(0xa5);
        char *buffer=reinterpret_cast<char *>(memory.data()+16);
        std::memcpy(buffer,"REAL_DEVICE_FINGERPRINT_SHOULD_NOT_REMAIN",39);
        std::string value(length,'x');
        int n=shield_properties::writeLegacy(key,value,buffer);
        std::string expected=key[0]=='r'&&length>=92?compatibility:value.substr(0,91);
        check(n==static_cast<int>(expected.size()));
        check(std::string(buffer)==expected);
        check(std::all_of(memory.begin(),memory.begin()+16,[](auto byte){return byte==0xa5;}));
        check(std::all_of(memory.end()-16,memory.end(),[](auto byte){return byte==0xa5;}));
        check(std::all_of(buffer+n,buffer+92,[](auto byte){return byte==0;}));
    }
    const std::string prefix(31,'n');
    for(std::string name:{prefix+"A",prefix+"B",std::string("ro.product.system_ext.manufacturer")}){
        prop_info info{name,std::string(256,'v')};
        errno=ENOENT;
        auto observed=shield_properties::snapshot(&info,original);
        check(observed.captured&&observed.name==name&&observed.value==info.value);
        check(errno==ENOENT);
    }
    check(!shield_properties::snapshot(nullptr,original).captured);
    prop_info info{"test","value"};
    check(!shield_properties::snapshot(&info,nullptr).captured);
    std::cout<<"PASS "<<checks<<" native boundary, zero-tail, full-name and errno checks\n";
}
