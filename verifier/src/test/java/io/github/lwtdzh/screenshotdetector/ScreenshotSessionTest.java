package io.github.lwtdzh.screenshotdetector;

import java.io.*;

/** Standalone JVM assertions for asynchronous source correlation and saved state. */
public final class ScreenshotSessionTest {
    private static int passed;
    private static void expect(ScreenshotSession session, int count, String message) {
        if (session.count() != count) throw new AssertionError(message + ": " + session.count());
        passed++;
    }
    public static void main(String[] args) throws Exception {
        ScreenshotSession session = new ScreenshotSession();
        expect(session, 0, "Fresh session");
        session.signal("OFFICIAL", null, 1000, 10000);
        session.signal("BINDER", null, 1001, 10001);
        session.signal("FILE_OBSERVER", "/Pictures/Screenshots/Screenshot_1.png", 1500, 10500);
        session.signal("FILE_POLL", "/Pictures/Screenshots/Screenshot_1.png", 1700, 10700);
        session.signal("MEDIA_POLL", "42", 1800, 10800);
        session.signal("MEDIA_CLIENT", "42", 1900, 10900);
        expect(session, 1, "Multiple routes for one screenshot");
        session.signal("OFFICIAL", null, 2000, 11000);
        session.signal("BINDER", null, 2001, 11001);
        session.signal("FILE_OBSERVER", "/Pictures/Screenshots/Screenshot_2.png", 2200, 11200);
        expect(session, 2, "Two quick official captures remain separate");
        session.signal("FILE_OBSERVER", "/Pictures/Screenshots/Screenshot_1.png", 9000, 19000);
        expect(session, 2, "Known file is not counted again after restart");
        ScreenshotSession files = new ScreenshotSession();
        files.signal("FILE_POLL", "/Screenshot_A.png", 1000, 10000);
        files.signal("FILE_OBSERVER", "/Screenshot_A.png", 1100, 10100);
        files.signal("FILE_OBSERVER", "/Screenshot_B.png", 1200, 10200);
        files.signal("FILE_POLL", "/Screenshot_B.png", 1300, 10300);
        expect(files, 2, "Distinct files across overlapping source routes");
        ScreenshotSession media = new ScreenshotSession();
        media.signal("MEDIA_POLL", "7", 1000, 10000);
        media.signal("MEDIA_CLIENT", "7", 1100, 10100);
        media.signal("MEDIA_CLIENT", "8", 1200, 10200);
        expect(media, 2, "Distinct media rows across overlapping routes");
        ScreenshotSession anonymous = new ScreenshotSession();
        anonymous.signal("ACCESSIBILITY_EVENT", null, 1000, 10000);
        anonymous.signal("ACCESSIBILITY_EVENT", null, 1100, 10100);
        anonymous.signal("NOTIFICATION_EVENT", null, 1200, 10200);
        expect(anonymous, 1, "Repeated anonymous overlay signals");
        anonymous.signal("ACCESSIBILITY_EVENT", null, 4000, 14000);
        expect(anonymous, 2, "Later anonymous event");
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(bytes)) { out.writeObject(session); }
        ScreenshotSession restored;
        try (ObjectInputStream input = new ObjectInputStream(new ByteArrayInputStream(bytes.toByteArray()))) {
            restored = (ScreenshotSession) input.readObject();
        }
        expect(restored, 2, "Saved session survives recreation");
        restored.signal("FILE_POLL", "/Pictures/Screenshots/Screenshot_2.png", 9000, 19000);
        expect(restored, 2, "Recreation preserves duplicate identities");
        if (restored.lastWallTime() != 11000) throw new AssertionError("Last screenshot time changed");
        passed++;
        System.out.println("PASS " + passed + " screenshot-session assertions");
    }
}
