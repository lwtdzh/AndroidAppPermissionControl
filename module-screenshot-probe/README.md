# ScreenshotProbe

An independent Android verification project for the screenshot protection module. Package ID: `io.github.lwtdzh.screenshotprobe`. App version: `0.1.0`.

Read the [shared agent guide](../AGENTS.md) and [workflow skill](../.trae/skills/android-permission-workflow/SKILL.md) before modifying its tests. Protection code lives in [module-screenshot-shield](../module-screenshot-shield/README.md); the visible detector has a separate project, [module-screenshot-detector](../module-screenshot-detector/README.md).

Read [PROJECT-RELATIONSHIPS.md](../PROJECT-RELATIONSHIPS.md) for companion APK requirements, framework scope, shared fixtures, and test order. When changing probe fixtures or assertions, review the shield behavior and detector tests that use them.

## Build

Open this directory in Android Studio or build from here:

```sh
./gradlew :app:assembleDebug
```

The debug APK is `app/build/outputs/apk/debug/app-debug.apk`. `./gradlew` also defaults to this debug build. The probe intentionally targets SDK 28 for legacy storage tests and is an emulator test app; its default avoids Google Play release-target checks. This project uses JDK 17, SDK 36, NDK `29.0.14206865`, and CMake `3.22.1`. Its build has no dependency on the protection or detector project's source code.

## Dedicated emulator tests

The prepared `ScreenshotShield_API36` emulator uses port `5584`, Magisk/Zygisk, and Vector 2.2. Its runtime files remain outside the collection in `~/Library/Application Support/ScreenshotShield/emulator/`.

```sh
scripts/start-emulator.sh -no-window
python3 scripts/emulator-test.py \
  --serial emulator-5584 \
  --module-apk /path/to/ScreenshotShield-0.1.3.apk \
  --output /tmp/screenshot-integration.json
python3 scripts/official-callback-test.py \
  --serial emulator-5584 \
  --output /tmp/screenshot-official-callback.json
```

`emulator-test.py` installs this project's debug APK and the selected module APK. Its default module path points to the sibling protection project's debug APK; build that APK first when using the default. If a signed release is already installed in the emulator, pass the matching signed module APK as shown above.

The integration test checks module-disabled, protected, and outside-scope behavior for Java/native files, MediaStore, actual URI grants, file events, and broadcasts. It also checks ordinary file, image, broadcast, and text controls. Notification and accessibility callback fixtures are labeled test content.

The official callback test uses a real SystemUI screenshot and requires baseline receipt before testing interception. ADB `screencap` is used only for image fixtures. These scripts reject non-emulator serials.

The visible detector's tests live in the sibling detector project's `scripts/` directory. Maintained protection verification records are in `../module-screenshot-shield/verification/`; detector records are in `../module-screenshot-detector/verification/`.

The relocated integration runner was executed successfully after this project split. Its record is [verification/layout-integration.json](verification/layout-integration.json).
