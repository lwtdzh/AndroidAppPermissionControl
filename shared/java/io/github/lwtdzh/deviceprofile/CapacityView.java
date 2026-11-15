package io.github.lwtdzh.deviceprofile;

/** Proportional read-only capacity views; never alters filesystem or memory state. */
public final class CapacityView {
    public static long total(long bytes,long blockSize) {
        return blockSize>0?bytes/blockSize:0;
    }
    public static long remaining(long original,long originalTotal,long targetTotal) {
        if(originalTotal<=0||targetTotal<=0)return 0;
        double fraction=(double)Math.max(0,Math.min(original,originalTotal))/originalTotal;
        return Math.max(0,Math.min(targetTotal,(long)(fraction*targetTotal)));
    }
    private CapacityView(){}
}
