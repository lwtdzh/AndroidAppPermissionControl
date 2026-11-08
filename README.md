# AndroidAppPermissionControl

Repository: [lwtdzh/AndroidAppPermissionControl](https://github.com/lwtdzh/AndroidAppPermissionControl).

A collection of Android apps and modules for restricting selected permissions or information access in user-selected apps. Screenshot detection protection is the first capability. Future projects can use Vector/Xposed, SukiSU/KernelSU, or other approaches to restrict additional permissions.

Each `module-*/` directory is a complete Android project with its own Gradle settings, wrapper, build configuration, and source code. Open that directory directly in Android Studio or as an agent workspace. The root contains shared instructions, agent skills, and host-side tools.

## Workspace structure

```text
AndroidAppPermissionControl/
├── README.md                         # Shared purpose and instructions
├── AGENTS.md                         # Instructions for every coding agent
├── PROJECT-RELATIONSHIPS.md           # Relationships and companion checks for all groups
├── .trae/skills/
│   └── android-permission-workflow/
│       └── SKILL.md                  # Shared development and verification workflow
├── scripts/
│   ├── build-all.sh                  # Build the independent Android projects
│   └── sign-apk.py                   # Sign APKs with the established external key
├── module-screenshot-shield/
│   ├── README.md
│   ├── settings.gradle
│   ├── build.gradle
│   ├── gradle/                       # This project's wrapper files
│   ├── gradlew
│   ├── app/                          # Screenshot protection module
│   ├── COVERAGE-AUDIT.md
│   └── verification/
├── module-screenshot-detector/
│   ├── README.md
│   ├── settings.gradle
│   ├── build.gradle
│   ├── gradle/
│   ├── gradlew
│   ├── app/                          # Visible screenshot detection log app
│   ├── scripts/
│   └── verification/
└── module-screenshot-probe/
    ├── README.md
    ├── settings.gradle
    ├── build.gradle
    ├── gradle/
    ├── gradlew
    ├── app/                          # Automated verification app
    └── scripts/
```

The `.trae/skills/` location allows TRAE to discover the skill. Its Markdown instructions and the root `AGENTS.md` can also be read by other agents.

## Current projects

| Android project | Purpose | Package |
| --- | --- | --- |
| [module-screenshot-shield](module-screenshot-shield/README.md) | Block screenshot detection in apps selected through Vector scope | `io.github.lwtdzh.screenshotshield` |
| [module-screenshot-detector](module-screenshot-detector/README.md) | Display real screenshot signals and manual read checks | `io.github.lwtdzh.screenshotdetector` |
| [module-screenshot-probe](module-screenshot-probe/README.md) | Verify hooks, file access, provider access, and ordinary-operation controls on a dedicated emulator | `io.github.lwtdzh.screenshotprobe` |

Existing app names, package IDs, versions, and signing identities are preserved. The protection project's Gradle name remains `ScreenshotShield`. The two standalone verification projects have their own Gradle names, `ScreenshotDetector` and `ScreenshotProbe`.

Read [PROJECT-RELATIONSHIPS.md](PROJECT-RELATIONSHIPS.md) for how the shield, detector, and probe work together, including framework scope, companion APKs, test fixtures, and test order. Future related subprojects must be documented in that same file.

## Build

The current projects use JDK 17, Android SDK 36, NDK `29.0.14206865`, and CMake `3.22.1`. Each project owns its SDK and Gradle configuration.

From the workspace root:

```sh
export JAVA_HOME=/opt/homebrew/opt/openjdk@17
export ANDROID_HOME=/opt/homebrew/share/android-commandlinetools

./scripts/build-all.sh
./module-screenshot-shield/gradlew -p ./module-screenshot-shield :app:assembleRelease
./module-screenshot-detector/gradlew -p ./module-screenshot-detector :app:assembleRelease
./module-screenshot-probe/gradlew -p ./module-screenshot-probe :app:assembleDebug
```

From within any individual project, use its own `./gradlew` to run that project's default build. Protection and detector projects default to release; the legacy-storage probe defaults to debug and retains its intentional SDK 28 target. APKs appear under that project's `app/build/outputs/apk/`. The shared helper uses those same defaults and also accepts a common task, for example `./scripts/build-all.sh :app:assembleDebug`.

For release signing, run the shared helper with an explicit input and output:

```sh
python3 scripts/sign-apk.py \
  module-screenshot-shield/app/build/outputs/apk/release/app-release-unsigned.apk \
  /tmp/ScreenshotShield-0.1.3.apk
```

The established signing state stays outside this workspace in `~/Library/Application Support/ScreenshotShield/signing/`. Keep that key when updating the existing apps.

## Adding another app or module

Create a new `module-<name>/` directory with a complete Android project, its own README, and its own build and packaging commands. Choose the implementation framework for that capability; different projects can use different frameworks.

Add the project to the table above. Keep its app-specific guidance, detector tools, and verification records inside that project. Put reusable agent instructions in the shared skill and reusable host tools in `scripts/`.

If it is related to another project, add or update the group's section in [PROJECT-RELATIONSHIPS.md](PROJECT-RELATIONSHIPS.md) and link that file from each participating project's README.

Each new restriction should have a corresponding detection or verification method. Compare the selected app before and after applying the restriction, and confirm ordinary operations still work. Record permission requirements, framework scope, platform versions, and whether the evidence came from a real system operation or test content.

## Starting a new agent

Read [AGENTS.md](AGENTS.md), [PROJECT-RELATIONSHIPS.md](PROJECT-RELATIONSHIPS.md), the relevant project's README, and the [shared workflow skill](.trae/skills/android-permission-workflow/SKILL.md). The protection project's audit explains current limitations; the verification records are stored beside the project they describe. Current code implements screenshot protection; other permission restrictions are future work.
