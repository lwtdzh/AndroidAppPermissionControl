package io.github.lwtdzh.screenshotshield;

import android.database.Cursor;
import android.database.CursorWrapper;

/** App sees its requested projection; extra provider metadata stays inside the filter. */
final class ProjectedCursor extends CursorWrapper {
    private final String[] names;
    ProjectedCursor(Cursor cursor, int count) {
        super(cursor);
        names = java.util.Arrays.copyOf(cursor.getColumnNames(), count);
    }
    private int check(int column) {
        if (column < 0 || column >= names.length) throw new android.database.CursorIndexOutOfBoundsException(column, names.length);
        return column;
    }
    @Override public int getColumnCount() { return names.length; }
    @Override public String[] getColumnNames() { return names.clone(); }
    @Override public String getColumnName(int column) { return names[check(column)]; }
    @Override public int getColumnIndex(String name) {
        int dot = name.lastIndexOf('.');
        if (dot >= 0) name = name.substring(dot + 1);
        for (int i = 0; i < names.length; i++) if (names[i].equalsIgnoreCase(name)) return i;
        return -1;
    }
    @Override public int getColumnIndexOrThrow(String name) {
        int column = getColumnIndex(name);
        if (column < 0) throw new IllegalArgumentException("column '" + name + "' does not exist");
        return column;
    }
    @Override public byte[] getBlob(int column) { return super.getBlob(check(column)); }
    @Override public String getString(int column) { return super.getString(check(column)); }
    @Override public short getShort(int column) { return super.getShort(check(column)); }
    @Override public int getInt(int column) { return super.getInt(check(column)); }
    @Override public long getLong(int column) { return super.getLong(check(column)); }
    @Override public float getFloat(int column) { return super.getFloat(check(column)); }
    @Override public double getDouble(int column) { return super.getDouble(check(column)); }
    @Override public int getType(int column) { return super.getType(check(column)); }
    @Override public boolean isNull(int column) { return super.isNull(check(column)); }
    @Override public void copyStringToBuffer(int column, android.database.CharArrayBuffer buffer) {
        super.copyStringToBuffer(check(column), buffer);
    }
}
