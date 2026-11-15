package com.heytap.openid;
/** Named debug-only proxy shape; never binds an OEM service. */
public interface IOpenID {
    final class Stub {
        public static final class Proxy {
            public String getSerID(String pkg,String signature,String type){return "fixture-heytap-"+type;}
        }
    }
}
