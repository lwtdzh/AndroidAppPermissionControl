import io.github.lwtdzh.deviceprofile.TypedProperty;

public final class TypedPropertyTest {
    private static int checks;
    private static void check(boolean ok,String message){if(!ok)throw new AssertionError(message);checks++;}
    public static void main(String[] args){
        for(String value:new String[]{"480","0480","+480","0x1e0"})
            check(TypedProperty.integer(value,-17)==480,"Typed decimal/hex "+value);
        for(String invalid:new String[]{"","bad","2147483648","9223372036854775808"})
            check(TypedProperty.integer(invalid,-17)==-17,"Typed default "+invalid);
        check(TypedProperty.number("-0x8000000000000000",1)==Long.MIN_VALUE,"Signed hex limit");
        check(TypedProperty.number("9223372036854775807",-17)==Long.MAX_VALUE,"Long maximum");
        check(TypedProperty.integer("-2147483648",-17)==Integer.MIN_VALUE,"Int minimum");
        for(String yes:new String[]{"1","y","yes","on","true"})check(TypedProperty.bool(yes,false),"True property");
        for(String no:new String[]{"0","n","no","off","false"})check(!TypedProperty.bool(no,true),"False property");
        check(TypedProperty.bool("invalid",true)&&!TypedProperty.bool("invalid",false),"Boolean defaults");
        System.out.println("PASS "+checks+" typed property number, overflow and boolean assertions");
    }
}
