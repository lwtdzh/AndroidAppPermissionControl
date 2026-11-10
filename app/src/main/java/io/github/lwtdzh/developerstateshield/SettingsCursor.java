package io.github.lwtdzh.developerstateshield;

import android.database.AbstractCursor;
import android.database.Cursor;
import android.database.ContentObserver;
import android.database.DataSetObserver;
import android.os.Bundle;

/** Retains row order and the caller's projection, including queries which request only value. */
final class SettingsCursor extends AbstractCursor {
    private final Cursor source;
    private final String[] names;
    private final int[] columns;
    private final int keyColumn;
    private final String selected;
    SettingsCursor(Cursor source, String[] projection, String selected) {
        this.source = source;
        this.selected = selected;
        keyColumn = source.getColumnIndex("name");
        names = projection == null ? source.getColumnNames() : projection.clone();
        columns = new int[names.length];
        for (int i = 0; i < names.length; i++) columns[i] = source.getColumnIndexOrThrow(names[i]);
    }
    private boolean zero(int column) {
        return "value".equals(names[column]) && DeveloperModule.hidden(
            keyColumn < 0 ? selected : source.getString(keyColumn));
    }
    @Override public int getCount() { return source.getCount(); }
    @Override public String[] getColumnNames() { return names.clone(); }
    @Override public boolean onMove(int oldPosition, int newPosition) { return source.moveToPosition(newPosition); }
    @Override public String getString(int column) { return zero(column) ? "0" : source.getString(columns[column]); }
    @Override public short getShort(int column) { return zero(column) ? 0 : source.getShort(columns[column]); }
    @Override public int getInt(int column) { return zero(column) ? 0 : source.getInt(columns[column]); }
    @Override public long getLong(int column) { return zero(column) ? 0L : source.getLong(columns[column]); }
    @Override public float getFloat(int column) { return zero(column) ? 0f : source.getFloat(columns[column]); }
    @Override public double getDouble(int column) { return zero(column) ? 0d : source.getDouble(columns[column]); }
    @Override public byte[] getBlob(int column) { return zero(column) ? new byte[]{'0'} : source.getBlob(columns[column]); }
    @Override public boolean isNull(int column) { return !zero(column) && source.isNull(columns[column]); }
    @Override public int getType(int column) { return zero(column) ? FIELD_TYPE_STRING : source.getType(columns[column]); }
    @Override public Bundle getExtras() { return source.getExtras(); }
    @Override public Bundle respond(Bundle extras) { return source.respond(extras); }
    @Override public void close() { source.close(); super.close(); }
    @Override public void deactivate() { source.deactivate(); super.deactivate(); }
    @Override public boolean requery() { mPos = -1; return source.requery(); }
    @Override public void registerContentObserver(ContentObserver observer) { source.registerContentObserver(observer); }
    @Override public void unregisterContentObserver(ContentObserver observer) { source.unregisterContentObserver(observer); }
    @Override public void registerDataSetObserver(DataSetObserver observer) { source.registerDataSetObserver(observer); }
    @Override public void unregisterDataSetObserver(DataSetObserver observer) { source.unregisterDataSetObserver(observer); }
}
