package io.github.lwtdzh.screenshotdetector;
import android.content.*;
import android.database.*;
import android.net.Uri;

/** Named vivo cursor shape for the dedicated AOSP emulator only. No OEM code. */
public final class VivoFixtureProvider extends ContentProvider {
    @Override public boolean onCreate(){return true;}
    @Override public Cursor query(Uri uri,String[] projection,String selection,String[] args,String order){
        MatrixCursor cursor=new MatrixCursor(new String[]{"value","fixture"});
        cursor.addRow(new Object[]{"fixture-vivo-"+uri.getLastPathSegment(),"ordinary-vivo-column"});return cursor;
    }
    @Override public String getType(Uri uri){return null;}
    @Override public Uri insert(Uri u,ContentValues v){throw new SecurityException("Fixture read only");}
    @Override public int update(Uri u,ContentValues v,String s,String[] a){throw new SecurityException("Fixture read only");}
    @Override public int delete(Uri u,String s,String[] a){throw new SecurityException("Fixture read only");}
}
