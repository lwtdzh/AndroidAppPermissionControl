#include <jni.h>
#include <sys/system_properties.h>
#include <ifaddrs.h>
#include <linux/if_packet.h>
#include <cstring>
#include <cstdio>
#include <string>
#include <sstream>
#include <vector>
#include <algorithm>

namespace {
template<size_t Size> struct Guarded {
    unsigned char before[16];
    char data[Size];
    unsigned char after[16];
    Guarded() { memset(before,0xa5,sizeof(before));memset(data,0,Size);memset(after,0xa5,sizeof(after)); }
    bool intact() const {
        for(auto value:before)if(value!=0xa5)return false;
        for(auto value:after)if(value!=0xa5)return false;
        return true;
    }
};
std::string bytes(const char *data,size_t count) {
    static constexpr char hex[]="0123456789abcdef";
    std::string out;out.reserve(count*2);
    for(size_t i=0;i<count;i++){unsigned char value=data[i];out+=hex[value>>4];out+=hex[value&15];}
    return out;
}
std::string quoted(const char *value) {
    std::string out="\"";
    for(const unsigned char *p=reinterpret_cast<const unsigned char *>(value?value:"");*p;p++){
        if(*p=='"' || *p=='\\'){out+='\\';out+=*p;}
        else if(*p<32){char escaped[7];snprintf(escaped,sizeof(escaped),"\\u%04x",*p);out+=escaped;}
        else out+=*p;
    }return out+'"';
}
void callback(void *cookie,const char *,const char *value,uint32_t){*static_cast<std::string *>(cookie)=value;}
void nested(void *cookie,const char *,const char *value,uint32_t){
    std::string before=value;char other[PROP_VALUE_MAX]={};
    __system_property_get("ro.product.brand",other);
    *static_cast<bool *>(cookie)=before==value;
}
struct ObjectRead {
    const prop_info *info = nullptr;
    std::string name, value;
    uint32_t callbackSerial = 0;
};
void objectCallback(void *cookie,const char *name,const char *value,uint32_t serial) {
    auto &out=*static_cast<ObjectRead *>(cookie);
    out.name=name;out.value=value;out.callbackSerial=serial;
}
ObjectRead readObject(const prop_info *info) {
    ObjectRead out;out.info=info;
    if(info)__system_property_read_callback(info,objectCallback,&out);
    return out;
}
std::string objectJson(const ObjectRead &object) {
    if(!object.info)return "null";
    const char *raw=reinterpret_cast<const char *>(object.info);
    uint32_t header=0,offset=0;
    memcpy(&header,raw,4);memcpy(&offset,raw+60,4);
    // Only inspect known Bionic layouts; this diagnostic does not parse arbitrary pointers.
    bool nameMatches=object.name.size()<=4096 &&
        !memcmp(raw+96,object.name.c_str(),object.name.size()+1);
    bool isLong=(header&(1u<<16))!=0;
    bool bounded=(!isLong && object.value.size()<92) ||
        (isLong && offset>=96 && offset<8192 && object.value.size()<8192);
    const char *value=bounded?(raw+(isLong?offset:4)):nullptr;
    bool matches=nameMatches && bounded && !memcmp(value,object.value.c_str(),object.value.size()+1);
    uint32_t expected=(isLong?50u:static_cast<uint32_t>(object.value.size()))<<24;
    if(isLong)expected|=1u<<16;
    uint32_t waited=0x12345678;timespec timeout{};
    bool changed=__system_property_wait(object.info,__system_property_serial(object.info),&waited,&timeout);
    std::ostringstream out;
    out<<"{\"name\":"<<quoted(object.name.c_str())<<",\"callback\":"<<quoted(object.value.c_str())
       <<",\"headerSerial\":"<<header<<",\"apiSerial\":"<<__system_property_serial(object.info)
       <<",\"callbackSerial\":"<<object.callbackSerial<<",\"expectedSerial\":"<<expected
       <<",\"long\":"<<(isLong?"true":"false")<<",\"longOffset\":"<<(isLong?offset:0)
       <<",\"rawMatchesCallback\":"<<(matches?"true":"false")
       <<",\"nameMatches\":"<<(nameMatches?"true":"false")
       <<",\"zeroWaitChanged\":"<<(changed?"true":"false")<<",\"waitOutput\":"<<waited<<"}";
    return out.str();
}
void objects(std::ostringstream &out) {
    out<<",\"propertyObjects\":{";
    bool comma=false;
    const char *keys[]={"ro.build.fingerprint","ro.product.model","ro.product.system_ext.manufacturer",
                        "ro.system_ext.build.id","ro.sf.lcd_density","sys.usb.config"};
    for(const char *key:keys) {
        if(comma)out<<',';comma=true;
        out<<quoted(key)<<':'<<objectJson(readObject(__system_property_find(key)));
    }
    static const prop_info *initial=__system_property_find("ro.build.fingerprint");
    static const prop_info *firstChanged=nullptr;
    auto *current=__system_property_find("ro.build.fingerprint");
    if(!firstChanged && current!=initial)firstChanged=current;
    out<<"},\"cachedPropertyObjects\":{\"initial\":"<<objectJson(readObject(initial))
       <<",\"firstChanged\":"<<objectJson(readObject(firstChanged))
       <<",\"firstChangedIsFresh\":"<<(firstChanged==current?"true":"false")<<"}";
    struct Enumeration {
        unsigned count=0;
        std::vector<std::pair<unsigned,ObjectRead>> selected;
    } enumeration;
    int result=__system_property_foreach([](const prop_info *info,void *cookie) {
        auto &all=*static_cast<Enumeration *>(cookie);
        ObjectRead item=readObject(info);
        if(item.name=="ro.build.fingerprint" || item.name=="ro.product.system_ext.manufacturer" ||
           item.name=="ro.system_ext.build.id" || item.name=="ro.sf.lcd_density" || item.name=="sys.usb.config")
            all.selected.emplace_back(all.count,item);
        ++all.count;
    },&enumeration);
    out<<",\"propertyEnumeration\":{\"result\":"<<result<<",\"count\":"<<enumeration.count<<",\"selected\":[";
    comma=false;
    for(const auto &entry:enumeration.selected) {
        if(comma)out<<',';comma=true;
        auto *nth=__system_property_find_nth(entry.first);
        auto *found=__system_property_find(entry.second.name.c_str());
        out<<"{\"index\":"<<entry.first<<",\"sameFindPointer\":"<<(found==entry.second.info?"true":"false")
           <<",\"sameNthPointer\":"<<(nth==entry.second.info?"true":"false")
           <<",\"object\":"<<objectJson(entry.second)<<"}";
    }
    out<<"],\"pastEndNull\":"<<(__system_property_find_nth(enumeration.count)==nullptr?"true":"false")<<"}";
}
}
extern "C" JNIEXPORT jstring JNICALL
Java_io_github_lwtdzh_screenshotdetector_DeviceRead_nativeSnapshot(JNIEnv *env,jclass) {
    std::ostringstream out;out<<"{\"properties\":{";bool comma=false;
    for(const char *key:{"ro.product.model","ro.product.brand","ro.product.manufacturer","ro.build.fingerprint",
        "ro.product.device","ro.product.name","ro.product.board","ro.product.vendor.device","ro.product.odm.name",
        "ro.product.system_ext.manufacturer","ro.product.system_ext.device","ro.product.system_ext.name",
        "ro.system.build.fingerprint","ro.system_ext.build.fingerprint","ro.vendor.build.fingerprint",
        "ro.product.build.fingerprint","ro.odm.build.fingerprint","ro.vendor.build.version.release",
        "ro.serialno","ro.hardware","ro.boot.selinux","sys.usb.config","appstate.probe.absent",
        "ro.sf.lcd_density","ro.build.id","ro.build.type","ro.build.tags",
        "ro.system.build.id","ro.system.build.type","ro.system.build.tags",
        "ro.system_ext.build.id","ro.system_ext.build.type","ro.system_ext.build.tags",
        "ro.vendor.build.id","ro.vendor.build.type","ro.vendor.build.tags",
        "ro.product.build.id","ro.product.build.type","ro.product.build.tags",
        "ro.odm.build.id","ro.odm.build.type","ro.odm.build.tags"}){
        if(comma)out<<',';comma=true;
        Guarded<PROP_VALUE_MAX> direct,read;
        Guarded<PROP_NAME_MAX> name;
        __system_property_get(key,direct.data);
        const prop_info *info=__system_property_find(key);std::string viaCallback;
        if(info){
            __system_property_read(info,name.data,read.data);
            __system_property_read_callback(info,callback,&viaCallback);
        }
        out<<quoted(key)<<":{\"get\":"<<quoted(direct.data)<<",\"read\":"<<(info?quoted(read.data):"null")
            <<",\"callback\":"<<(info?quoted(viaCallback.c_str()):"null")<<"}";
    }
    out<<"},\"legacyControls\":{";comma=false;
    for(const char *key:{"ro.build.fingerprint","ro.system.build.fingerprint","ro.system_ext.build.fingerprint",
        "ro.vendor.build.fingerprint","ro.product.build.fingerprint","ro.odm.build.fingerprint",
        "ro.product.system_ext.manufacturer","ro.product.system_ext.device","ro.product.system_ext.name",
        "sys.usb.config","appstate.probe.absent"}){
        if(comma)out<<',';comma=true;
        Guarded<PROP_VALUE_MAX> direct,read,withoutName;Guarded<PROP_NAME_MAX> name;
        int getLength=__system_property_get(key,direct.data),readLength=0,nullNameLength=0;
        const prop_info *info=__system_property_find(key);
        if(info){
            readLength=__system_property_read(info,name.data,read.data);
            nullNameLength=__system_property_read(info,nullptr,withoutName.data);
        }
        bool safe=direct.intact()&&read.intact()&&withoutName.intact()&&name.intact();
        out<<quoted(key)<<":{\"buffersIntact\":"<<(safe?"true":"false")
            <<",\"getLength\":"<<getLength<<",\"readLength\":"<<readLength
            <<",\"nullNameLength\":"<<nullNameLength<<",\"readName\":"<<(info?quoted(name.data):"null")
            <<",\"nullNameValue\":"<<(info?quoted(withoutName.data):"null")
            <<",\"getBytes\":"<<quoted(bytes(direct.data,PROP_VALUE_MAX).c_str())
            <<",\"readBytes\":"<<(info?quoted(bytes(read.data,PROP_VALUE_MAX).c_str()):"null")
            <<",\"nullNameBytes\":"<<(info?quoted(bytes(withoutName.data,PROP_VALUE_MAX).c_str()):"null")<<"}";
    }
    out<<"},\"interfaces\":{";comma=false;bool okay=true;
    for(int repeat=0;repeat<64;repeat++){
        ifaddrs *head=nullptr;if(getifaddrs(&head)){okay=false;break;}
        if(repeat==0)for(auto *item=head;item;item=item->ifa_next){
            if(!item->ifa_addr || item->ifa_addr->sa_family!=AF_PACKET)continue;
            auto *address=reinterpret_cast<sockaddr_ll *>(item->ifa_addr);if(address->sll_halen!=6)continue;
            char mac[18];snprintf(mac,sizeof(mac),"%02x:%02x:%02x:%02x:%02x:%02x",
                address->sll_addr[0],address->sll_addr[1],address->sll_addr[2],address->sll_addr[3],address->sll_addr[4],address->sll_addr[5]);
            if(comma)out<<',';comma=true;out<<quoted(item->ifa_name)<<':'<<quoted(mac);
        }
        freeifaddrs(head);
    }
    bool stable=false;
    const prop_info *model=__system_property_find("ro.product.model");
    if(model)__system_property_read_callback(model,nested,&stable);
    out<<"},\"interfaceFreeControl\":"<<(okay?"true":"false")
        <<",\"propertyCallbackLifetimeControl\":"<<(stable?"true":"false");
    objects(out);out<<"}";
    return env->NewStringUTF(out.str().c_str());
}
