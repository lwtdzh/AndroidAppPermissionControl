#include "property-view.h"
#include <cassert>
#include <thread>
#include <vector>
#include <iostream>

int main() {
    shield_properties::ReadOnlyViews views;
    const std::string name="ro.product.system_ext.manufacturer";
    std::vector<const void *> retained;
    for(size_t length:{0,1,48,91,92,128,256,4096}) {
        std::string value(length,'T');
        auto *pointer=views.get(name,value);assert(pointer && views.owns(pointer));
        auto *raw=static_cast<const char *>(pointer);
        assert(!memcmp(raw+96,name.c_str(),name.size()+1));
        uint32_t serial=0,offset=0;memcpy(&serial,raw,4);memcpy(&offset,raw+60,4);
        bool isLong=length>=92;
        assert(serial==((isLong?50u:static_cast<uint32_t>(length))<<24|(isLong?1u<<16:0)));
        assert(!memcmp(raw+(isLong?offset:4),value.c_str(),value.size()+1));
        if(isLong) {
            assert(offset==96+name.size()+1);
            assert(!strcmp(raw+4,views.compatibility));
        } else for(size_t i=length+1;i<92;i++)assert(raw[4+i]==0);
        assert(views.get(name,value)==pointer);
        views.remember(pointer,"wrong");assert(views.name(pointer).empty());
        retained.push_back(pointer);
    }
    int original=0;views.remember(&original,name.c_str());
    assert(!views.owns(&original) && views.name(&original)==name);
    assert(!views.get("sys.usb.config","x"));
    assert(!views.get(std::string("ro.x\0y",6),"x"));
    assert(!views.get("ro.x",std::string("a\0b",3)));
    assert(!views.get("ro.x",std::string(1024*1024+1,'x')));
    std::vector<std::thread> readers;
    for(int i=0;i<8;i++)readers.emplace_back([&] {
        for(int n=0;n<200;n++) {
            assert(views.get(name,std::string(128,'T'))==retained[5]);
            assert(views.owns(retained[1]));
            assert(views.name(&original)==name);
        }
    });
    for(auto &reader:readers)reader.join();
    // New profiles never rewrite previously published pointers.
    assert(!strcmp(static_cast<const char *>(retained[2])+4,std::string(48,'T').c_str()));
    std::cout<<"PASS readonly layout, bounds, memoization, lifetime and 8 concurrent readers\n";
}
