# Agent guide

Read `README.md`, `PROJECT-RELATIONSHIPS.md`, `docs/ARCHITECTURE.md` and `.trae/skills/android-permission-workflow/SKILL.md` before changing protection, policy, packaging or verification.

## Project layout

- This root is one Gradle project with one wrapper: `:app` is AppStateShield and `:verifier` is the retained verification APK.
- Do not create independent projects for individual blocking methods. Add methods to the main app and matching checks to the verifier.
- Main package: `io.github.lwtdzh.appstateshield`; settings retain Vector MODULE_SETTINGS/INFO. The optional Launcher alias defaults disabled; only the user's icon switch enables it.
- Verifier retains `io.github.lwtdzh.screenshotdetector` and the existing external signing identity. Debug sampleA/sampleB flavors are temporary targets for independent UID checks, not production apps.
- Keep shared scripts in `scripts/`, current results in `verification/`, historical records in `verification/legacy/`.

## Policy and hooks

- Vector alone owns scope. Unconfigured scoped apps enable every implemented and future method.
- Persist only stable disabled method IDs per package. Preserve unknown IDs. Removing customization restores defaults.
- Machine spoofing is a separate default-off whitelist, never a seventh default-on Methods ID. DeviceStore saves fixed per-package identifiers and selected fields; getters must not generate random values. Keep the original six-method policy unchanged.
- Every category gates its stored parameters through the app master + category control + individual field selection. idsEnabled, environmentEnabled, modelEnabled and locationEnabled default false; networkMode defaults off for new/missing documents. Preserve existing explicit flags/modes, values, unknown fields and selections. Unknown fields stay stored but cannot apply without catalog category metadata.
- Category headers always show on/off, or one of off / simulate / no_sim for network. Every field has an independent switch, including identifiers/model/environment. Presets, category refresh, save and recreation preserve category controls; never force cellular selections on in simulate mode.
- Location has a default-off master. DeviceProfile.get requires machine + location + field; old profiles and presets never implicitly opt in. Region selection fills only latitude/longitude/accuracy and preserves the master. Cell fields belong to network.
- Network modes are off / simulate / no_sim (default off), gated by the machine master. Simulate controls the virtual ready SIM/registration state while each selected field controls only its saved parameter; unselected virtual fields retain empty/unknown constructor values, never an unselected saved value or a synthetic fallback. Keep sync/async/Parcel representations consistent. Off restores actual values/errors; no_sim clears cellular data without clearing modem IMEIs. Wi-Fi/Bluetooth remain independent fields; refresh preserves every category control.
- No credentials, signing keys, account data, notification bodies or clipboard contents in logs or commits.
- PolicyProvider is read-only and validates requested package against calling UID. Never introduce exported writes or another app's policy reads.
- Install hooks before Application.attach delegates to app lifecycle. Policy changes apply on the target's next cold start.
- Device profiles refresh through notification and two-second polling while Activities are visible; stop cyclic Binder reads when the last Activity stops and refresh immediately on return. Repeated getters use immutable local snapshots; static fields and app caches may require a cold start. Restore original Build fields and native values when a profile is disabled.
- Keep VPN/proxy and developer/debug controls independent; native libraries load only for enabled methods.
- Preserve screenshot syscall assembly dispatch, clone child stack and six arguments. Vector native_init runs under loader locks: do not use dlopen there; use RTLD_DEFAULT. Retain RO linker-view handling and safe paired native allocations/releases.
- Preserve recognized pre-existing external ARM64 entry redirects instead of chaining an inline hook over a packer's guard. Log skipped symbol names only. Retained entries have limited native screenshot coverage; successful startup is not evidence that those reads are blocked.
- SELinux is an independent `selinux` method. Report Enforcing only inside injected targets; never change the system mode or context. Preserve read failures, EOF and descriptor ownership. Direct syscalls, un-injected subprocesses and retained external entries remain limitations.

## Verification and builds

- Verifier 0.4.12 runs read-only environment checks on entry via EnvironmentOverview → EnvironmentProbe, using environmentprobe.cpp and the bounded AttestationRecord DER parser. Do not run SelinuxProbe.snapshot automatically: it includes active traffic/file fixtures. Never execute su, change system modes, request device IDs, or enumerate/delete unrelated keystore aliases as part of automatic checks.
- Preserve the documented inability reasons in docs/DETECTOR-LIMITATIONS-0.4.11.md: real Vector/Zygisk mapped libraries still expose injection; Native Detector's precise enumeration algorithm is unconfirmed. The original AOSP emulator already has a test attestation root, software attestation and KeyMint, unlocked/unverified boot, zero verifiedBootKey and verifiedBootHash. A process hook cannot supply trusted CA signing, TEE/StrongBox isolation, or an AVB chain, nor edit signed fields while preserving the original signature. Missing device ID attestation is unsupported validation, not a newly observed failure. Do not attribute original-image results to installing Root or extrapolate them to vivo.
- Environment results describe the injected app's local view. EACCES/unsupported reads stay UNKNOWN. Known-path checks are not equivalent to Native Detector/Ruru algorithms. Google SPKI pins are public and dated in verifier/src/main/assets/attestation-trust-anchors.json; unknown roots may be vendor roots. Offline signature/date/challenge checks do not establish online revocation or remote integrity, and boot properties can be hooked. Keep these distinctions in UI/docs/reports.

- Use `docs/TEST-EXECUTION-POLICY.md` to select tests before running `docs/TEST-MANUAL.md`. The manual is a case catalog, not a requirement to run everything after each edit. Record affected cases and reusable evidence. Run 64 combinations for a new baseline or changes to policy/shared hooks/interactions, not every APK hash change. Preserve passed cases on interruption; do not restart the whole chain.
- Verify UI drafts/save/cancel through real UI. Combination and field-restoration executors use dedicated-emulator atomic preference fixtures after representative UI persistence checks; preserve unknown settings, other packages and profile values. Never add exported production writes. Resume checks installed bytes and real fixtures, keeps passing same-APK cases and records durations. Cross-APK reuse requires the pinned build-input and integration evidence validated by scripts/test_evidence.py.
- Use `scripts/selinux-test.py` for real Permissive/Enforcing baselines; save its original state outside git and restore it before shutdown. Stop after selected checks pass; broaden only for a related change, failure or new evidence. Track durations and apply the execution policy's time/retry limits.
- A zero result without a real enabled baseline, correct permissions and live callback is not proof of blocking.
- Follow docs/DEVICE-TEST-MATRIX.md and scripts/machine-test.py for device spoofing. OEM classes under verifier/src/debug are synthetic fixtures; release APKs must exclude them. An AOSP SDK-shaped fixture is not evidence for a vivo/OPPO/Xiaomi ROM.
- ADB tests may use only the dedicated ScreenshotShield_API36 emulator-5584. Preserve unrelated modules/scopes, settings, grants, services and fixtures. Never deploy to a physical device without user authorization.
- Build with root `scripts/build-all.sh` using JDK17, SDK36, NDK29.0.14206865, CMake3.22.1. Four ABI compilation is distinct from runtime validation.
- Verifier targets28 intentionally to retain legacy file access for diagnostic controls; main module targets36. Official screenshot logging requires API34; older devices use the state probe.
- Sign through `scripts/sign-apk.py`; key state stays outside repository. Do not commit or push without user request.
- Update architecture, relationships and manual when adding methods, changing packages, interfaces or test fixtures.
