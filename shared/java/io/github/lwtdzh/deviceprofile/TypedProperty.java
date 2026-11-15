package io.github.lwtdzh.deviceprofile;

/** Android property getters preserve caller defaults for invalid text or overflow. */
public final class TypedProperty {
    public static long number(String value,long fallback) {
        if(value==null)return fallback;
        try {
            int start=value.startsWith("-")||value.startsWith("+")?1:0;
            if(value.regionMatches(true,start,"0x",0,2))
                return Long.parseLong(value.substring(0,start)+value.substring(start+2),16);
            return Long.parseLong(value,10);
        } catch(NumberFormatException invalid){return fallback;}
    }
    public static int integer(String value,int fallback) {
        long number=number(value,fallback);
        return number<Integer.MIN_VALUE||number>Integer.MAX_VALUE?fallback:(int)number;
    }
    public static boolean bool(String value,boolean fallback) {
        if(value==null)return fallback;
        switch(value){
            case "1":case "y":case "yes":case "on":case "true":return true;
            case "0":case "n":case "no":case "off":case "false":return false;
            default:return fallback;
        }
    }
    private TypedProperty(){}
}
