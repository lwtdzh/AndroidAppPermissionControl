package io.github.lwtdzh.screenshotshield;

import android.database.Cursor;
import android.database.CursorWrapper;
import java.util.ArrayList;
import java.util.List;
import java.util.function.Predicate;

/** Keeps column types/extras/window ownership with the original cursor; maps visible positions. */
final class FilteredCursor extends CursorWrapper {
    private int[] rows;
    private int position = -1;
    private final Predicate<Cursor> extra;
    FilteredCursor(Cursor source, Predicate<Cursor> extra) {
        super(source); this.extra = extra; rebuild();
    }

    static Cursor wrap(Cursor source) {
        return wrap(source, null);
    }
    static Cursor wrap(Cursor source, Predicate<Cursor> extra) {
        if (source == null || source instanceof FilteredCursor) return source;
        boolean hasMetadata = false;
        for (String name : new String[]{"_display_name", "_data", "relative_path", "document_id"}) {
            if (source.getColumnIndex(name) >= 0) hasMetadata = true;
        }
        return hasMetadata || extra != null ? new FilteredCursor(source, extra) : source;
    }
    private void rebuild() {
        Cursor source = getWrappedCursor();
        int oldPosition = source.getPosition();
        List<Integer> indexes = new ArrayList<>();
        int[] columns = {
            source.getColumnIndex("_display_name"), source.getColumnIndex("_data"),
            source.getColumnIndex("relative_path"), source.getColumnIndex("document_id")
        };
        for (int row = 0; row < source.getCount(); row++) {
            if (!source.moveToPosition(row)) break;
            boolean hidden = false;
            for (int column : columns) {
                if (column >= 0 && !source.isNull(column) && Rules.screenshot(source.getString(column))) {
                    hidden = true;
                    break;
                }
            }
            if (!hidden && extra != null) hidden = extra.test(source);
            if (!hidden) indexes.add(row);
        }
        rows = new int[indexes.size()];
        for (int i = 0; i < rows.length; i++) rows[i] = indexes.get(i);
        source.moveToPosition(oldPosition);
    }
    @Override public int getCount() { return rows.length; }
    @Override public int getPosition() { return position; }
    @Override public boolean moveToPosition(int wanted) {
        if (wanted >= rows.length) {
            position = rows.length;
            getWrappedCursor().moveToPosition(getWrappedCursor().getCount());
            return false;
        }
        if (wanted < 0) {
            position = -1;
            getWrappedCursor().moveToPosition(-1);
            return false;
        }
        boolean moved = getWrappedCursor().moveToPosition(rows[wanted]);
        if (moved) position = wanted;
        return moved;
    }
    @Override public boolean move(int offset) { return moveToPosition(position + offset); }
    @Override public boolean moveToFirst() { return moveToPosition(0); }
    @Override public boolean moveToLast() { return moveToPosition(rows.length - 1); }
    @Override public boolean moveToNext() { return moveToPosition(position + 1); }
    @Override public boolean moveToPrevious() { return moveToPosition(position - 1); }
    @Override public boolean isFirst() { return rows.length > 0 && position == 0; }
    @Override public boolean isLast() { return rows.length > 0 && position == rows.length - 1; }
    @Override public boolean isBeforeFirst() { return rows.length == 0 || position < 0; }
    @Override public boolean isAfterLast() { return rows.length == 0 || position >= rows.length; }
    @Override @SuppressWarnings("deprecation") public boolean requery() {
        if (!super.requery()) return false;
        rebuild();
        position = -1;
        return true;
    }
}
