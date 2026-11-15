package com.bun.miitmdid.interfaces;
/** Public SDK interface shape only, without vendor code. */
public interface IdSupplier {
    String getOAID();
    String getVAID();
    String getAAID();
}
