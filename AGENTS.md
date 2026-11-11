# Agent guide

Read `README.md`, `PROJECT-RELATIONSHIPS.md`, `docs/ARCHITECTURE.md` and `.trae/skills/android-permission-workflow/SKILL.md` before changing protection, policy, packaging or verification.

## Project layout

- This root is one Gradle project with one wrapper: `:app` is AppStateShield and `:verifier` is the retained verification APK.
- Do not create independent projects for individual blocking methods. Add methods to the main app and matching checks to the verifier.
- Main package: `io.github.lwtdzh.appstateshield`; main settings have Vector MODULE_SETTINGS/INFO only, no LAUNCHER.
- Verifier retains `io.github.lwtdzh.screenshotdetector` and the existing external signing identity. Debug sampleA/sampleB flavors are temporary targets for independent UID checks, not production apps.
- Keep shared scripts in `scripts/`, current results in `verification/`, historical records in `verification/legacy/`.

## Policy and hooks

- Vector alone owns scope. Unconfigured scoped apps enable every implemented and future method.
- Persist only stable disabled method IDs per package. Preserve unknown IDs. Removing customization restores defaults.
- No credentials, signing keys, account data, notification bodies or clipboard contents in logs or commits.
- PolicyProvider is read-only and validates requested package against calling UID. Never introduce exported writes or another app's policy reads.
- Install hooks before Application.attach delegates to app lifecycle. Policy changes apply on the target's next cold start.
- Keep VPN/proxy and developer/debug controls independent; native libraries load only for enabled methods.
- Preserve screenshot syscall assembly dispatch, clone child stack and six arguments. Vector native_init runs under loader locks: do not use dlopen there; use RTLD_DEFAULT. Retain RO linker-view handling and safe paired native allocations/releases.
- Preserve recognized pre-existing external ARM64 entry redirects instead of chaining an inline hook over a packer's guard. Log skipped symbol names only. Retained entries have limited native screenshot coverage; successful startup is not evidence that those reads are blocked.
- SELinux is an independent `selinux` method. Report Enforcing only inside injected targets; never change the system mode or context. Preserve read failures, EOF and descriptor ownership. Direct syscalls, un-injected subprocesses and retained external entries remain limitations.

## Verification and builds

- Follow `docs/TEST-MANUAL.md`; exercise UI drafts/save/cancel, 64 policy combinations, independent packages, early lifecycle, real system events, actual URI grants, and ordinary operations. Use `scripts/selinux-test.py` for real Permissive/Enforcing baselines; save its original state outside git and restore it before shutdown.
- A zero result without a real enabled baseline, correct permissions and live callback is not proof of blocking.
- ADB tests may use only the dedicated ScreenshotShield_API36 emulator-5584. Preserve unrelated modules/scopes, settings, grants, services and fixtures. Never deploy to a physical device without user authorization.
- Build with root `scripts/build-all.sh` using JDK17, SDK36, NDK29.0.14206865, CMake3.22.1. Four ABI compilation is distinct from runtime validation.
- Verifier targets28 intentionally to retain legacy file access for diagnostic controls; main module targets36. Official screenshot logging requires API34; older devices use the state probe.
- Sign through `scripts/sign-apk.py`; key state stays outside repository. Do not commit or push without user request.
- Update architecture, relationships and manual when adding methods, changing packages, interfaces or test fixtures.
