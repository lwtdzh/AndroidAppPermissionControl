---
name: android-permission-workflow
description: Develop and verify the integrated AppStateShield Vector module and its retained verifier.
---

# Android permission workflow

Read root README, AGENTS, PROJECT-RELATIONSHIPS and docs/ARCHITECTURE.

The root is one Gradle build, with `app/` for all blocking methods and `verifier/` for all observation checks. Do not split methods into separate apps. Keep the verifier package/signature stable. Main settings open from Vector; the optional launcher icon defaults off and is controlled by the user's setting.

Add a stable Methods ID and store only disabled IDs. Unconfigured and future methods default enabled. Provider requests must validate calling UID. Settings save drafts atomically; target cold-start applies them. Adding an app customization does not change Vector scope.

When extending screenshot hooks, read `verification/legacy/module-screenshot-shield-COVERAGE-AUDIT.md` and preserve native syscall/clone and linker handling. VPN and proxy, developer and debugging stay independently selectable.

Add matching verifier reads for every restriction. Establish real system baseline signals and ordinary-operation controls. Constructed screenshot names, notification objects and clipboard tests must remain labeled fixtures. A real SystemUI screenshot and actual system picker grant need separate evidence.

Select affected cases using `docs/TEST-EXECUTION-POLICY.md`, then execute those cases from `docs/TEST-MANUAL.md` on dedicated emulator-5584 only. Do not run the entire catalog after each patch or invalidate every result solely because an APK hash changed. Preserve provenance when reusing unchanged behavior; final artifact checks and final restoration remain current. Complete one 64-combination baseline for changes that affect policy/shared hooks/interactions, and resume passed combinations after interruption. If the current executor or packaging gate cannot follow the policy, adjust it before another full chain. Restore all original scopes, settings, grants, service state and fixtures. Do not expose private data in logs.

The current matrix/all-field executors use atomic dedicated-emulator preference fixtures after representative UI persistence checks. Keep fixed identifiers, unknown IDs, unrelated preferences and the original snapshot. Same-APK passed cases resume without rewriting evidence. Cross-APK reuse is checked by scripts/test_evidence.py against build-time inputs, unchanged hooks/readers/assertions and fresh enabled/update/disable integration; never retrofit a source snapshot onto old evidence.

For location/network changes, use `scripts/location-ui-test.py`: location stays default-off and a region changes only three coordinate fields. All network modes must align SIM state, subscriptions, carrier/service state and sync/async/Parcel cells, including SIM-present mode. Category refresh changes only its category and preserves master/mode state. Keep six-method historical tests attributed to their original APK; do not rerun 64 combinations for changes confined to the device-profile adapters.

Build through the root wrapper or `scripts/build-all.sh`, using JDK17, SDK36, NDK29.0.14206865 and CMake3.22.1. Sign with `scripts/sign-apk.py` and the existing external key. Record exact tested ABI/platform, test failures fixed, and unsupported baselines. SELinux validation requires real Permissive/Enforcing reads and ordinary FD controls through `scripts/selinux-test.py`; never change mode on a physical device for testing.
