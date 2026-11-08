package io.github.lwtdzh.screenshotdetector;

import android.app.Activity;
import android.os.Binder;
import android.os.IBinder;
import android.os.Parcel;
import android.os.RemoteException;

final class RawCapture implements AutoCloseable {
    private final IBinder service, token, observer;
    private final int unregister;
    RawCapture(Activity activity, int[] codes) throws RemoteException {
        service = Native.activityTask();
        // LayoutParams.token is the Activity token. View.getApplicationWindowToken()
        // can instead return the ViewRoot's IWindow Binder, which registers no observer.
        token = activity.getWindow().getAttributes().token;
        if (service == null || token == null) throw new UnsupportedOperationException("No activity Binder");
        unregister = codes[1];
        observer = new Binder() {
            @Override protected boolean onTransact(int code, Parcel data, Parcel reply, int flags)
                throws RemoteException {
                if (code == FIRST_CALL_TRANSACTION) {
                    data.enforceInterface("android.app.IScreenCaptureObserver");
                    data.enforceNoDataAvail();
                    Signals.emit(Source.BINDER, null);
                    if (reply != null) reply.writeNoException();
                    return true;
                }
                return super.onTransact(code, data, reply, flags);
            }
        };
        transact(codes[0]);
    }
    private void transact(int code) throws RemoteException {
        Parcel data = Parcel.obtain(), reply = Parcel.obtain();
        try {
            data.writeInterfaceToken("android.app.IActivityTaskManager");
            data.writeStrongBinder(token); data.writeStrongBinder(observer);
            if (!service.transact(code, data, reply, 0)) throw new UnsupportedOperationException("Rejected");
            reply.readException();
        } finally { data.recycle(); reply.recycle(); }
    }
    @Override public void close() throws RemoteException { transact(unregister); }
}
