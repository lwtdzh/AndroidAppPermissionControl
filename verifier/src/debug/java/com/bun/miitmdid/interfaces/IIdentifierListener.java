package com.bun.miitmdid.interfaces;

/** Debug-only MSA callback shape. */
public interface IIdentifierListener {
    void OnSupport(boolean supported, IdSupplier supplier);
}
