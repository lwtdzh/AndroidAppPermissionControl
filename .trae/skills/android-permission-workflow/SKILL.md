---
name: android-permission-workflow
description: Develop and verify the integrated AppStateShield Vector module and its retained verifier.
---

# Android permission workflow

Read root README, AGENTS, PROJECT-RELATIONSHIPS and docs/ARCHITECTURE.

The root is one Gradle build, with `app/` for all blocking methods and `verifier/` for all observation checks. Do not split methods into separate apps. Keep the verifier package/signature stable. Main settings open from Vector and have no launcher icon.

Add a stable Methods ID and store only disabled IDs. Unconfigured and future methods default enabled. Provider requests must validate calling UID. Settings save drafts atomically; target cold-start applies them. Adding an app customization does not change Vector scope.

When extending screenshot hooks, read `verification/legacy/module-screenshot-shield-COVERAGE-AUDIT.md` and preserve native syscall/clone and linker handling. VPN and proxy, developer and debugging stay independently selectable.

Add matching verifier reads for every restriction. Establish real system baseline signals and ordinary-operation controls. Constructed screenshot names, notification objects and clipboard tests must remain labeled fixtures. A real SystemUI screenshot and actual system picker grant need separate evidence.

Execute the persisted `docs/TEST-MANUAL.md` on dedicated emulator-5584 only. Restore all original scopes, settings, grants, service state and fixtures. Do not expose private data in logs.

Build through the root wrapper or `scripts/build-all.sh`, using JDK17, SDK36, NDK29.0.14206865 and CMake3.22.1. Sign with `scripts/sign-apk.py` and the existing external key. Record exact tested ABI/platform, test failures fixed, and unsupported baselines. Never describe pending SELinux as implemented.
