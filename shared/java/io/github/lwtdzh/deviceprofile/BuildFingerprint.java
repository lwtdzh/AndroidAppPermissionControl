package io.github.lwtdzh.deviceprofile;

import java.util.regex.*;

/** Android's documented brand/product/device:release/id/incremental:type/tags format. */
public final class BuildFingerprint {
    private static final Pattern FORMAT=Pattern.compile(
        "([^/\\s:]+)/([^/\\s:]+)/([^/\\s:]+):([^/\\s:]+)/([^/\\s:]+)/([^/\\s:]+):([^/\\s:]+)/([^/\\s:]+)");
    public final String brand,product,device,release,id,incremental,type,tags;
    private BuildFingerprint(Matcher m) {
        brand=m.group(1);product=m.group(2);device=m.group(3);release=m.group(4);
        id=m.group(5);incremental=m.group(6);type=m.group(7);tags=m.group(8);
    }
    public static BuildFingerprint parse(String value) {
        if(value==null)return null;
        Matcher m=FORMAT.matcher(value);
        return m.matches()?new BuildFingerprint(m):null;
    }
    public String metadata(String field) {
        switch(field) { case "ID":return id;case "TYPE":return type;case "TAGS":return tags;default:return null; }
    }
}
