---
name: android-permission-workflow
description: Develop and verify Android permission restrictions in this workspace. Use for new modules, Vector or SukiSU changes, detector updates, builds, and device tests.
---

# Android permission workflow

Read the collection's `README.md`, `AGENTS.md`, and `PROJECT-RELATIONSHIPS.md`, then the target project's README. Use the project table to find the responsible Android project and the relationship record to identify companion work.

## Locate the implementation

- Put a new app or module in `module-<name>/` with its own Gradle wrapper, settings, build configuration, `app/`, and README.
- Keep `module-screenshot-shield` as the existing Vector/Xposed protection project. Its current app scope is controlled by Vector.
- Use `module-screenshot-detector` for visible signal/read checks and `module-screenshot-probe` for dedicated-emulator verification.
- Keep app-specific code and packaging inside its Android project. Use the collection's `scripts/` only for reusable host tooling.
- Record every group of related subprojects in the root `PROJECT-RELATIONSHIPS.md`. Add future groups to that same file and link it from their READMEs.

## Define the restriction

Identify the selected app, permission or observation path, required access, framework injection scope, and expected allowed operations. For a new capability, choose Vector/Xposed, SukiSU/KernelSU, or another mechanism based on the actual system entry point.

Read the protection project's `COVERAGE-AUDIT.md` before extending screenshot hooks. Preserve current package IDs and labels unless the user asks to change them.

## Verify the result

Add a detector or test for each new restriction. Obtain a real baseline signal before counting a zero result as protection. Record which tests use system-generated events and which use explicitly labeled test content.

Include an ordinary-operation control. For media URI access, obtain an actual system grant; for notification and clipboard tests, verify service connection and foreground access. Avoid printing image paths, notification bodies, clipboard values, or account data.

Preserve device scope, service settings, and private clipboard state during temporary tests. Restore them and remove only the test content created by the run.

## Build and package

Build through the target project's own `gradlew` with `-p` if running from the collection root. The current projects require JDK 17, SDK 36, NDK `29.0.14206865`, and CMake `3.22.1`.

Use the collection's `scripts/build-all.sh` for a shared build check and `scripts/sign-apk.py` for release signing. Keep the established external signing key for updates to existing apps.

Update the target project's README and verification records. Update `PROJECT-RELATIONSHIPS.md` when relationships, shared interfaces, paths, version requirements, or test fixtures change. Update other root guidance when the instruction applies across projects. When moving code, verify each project's independent build and the paths used by companion tests.
