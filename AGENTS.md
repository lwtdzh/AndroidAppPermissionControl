# Agent guide

Read the root `README.md`, `PROJECT-RELATIONSHIPS.md`, the target project's `README.md`, and `.trae/skills/android-permission-workflow/SKILL.md` before changing a permission restriction, detector, build, packaging, or device workflow.

## Project ownership

- Treat each `module-*/` directory as an independent Android project. It owns `settings.gradle`, `build.gradle`, the Gradle wrapper, and `app/`.
- Run Gradle from that project or use its wrapper with `-p <project-directory>`. The collection root is not a Gradle build.
- Keep app-specific instructions, test tools, and verification records inside the relevant project. Keep shared instructions and reusable host tools at the collection root.
- Add future apps or modules in new `module-<name>/` directories and register them in the root README.
- Whenever two or more subprojects are related, record their roles, dependencies, shared assumptions, and companion checks in the root `PROJECT-RELATIONSHIPS.md`. Add future groups to that same file and link it from each participating project's README.
- Before changing one project, read its relationship section and review the affected companion projects. Update that section when paths, package IDs, interfaces, version requirements, fixtures, or relationships change.
- Preserve existing app labels, package IDs, version numbers, and signing identities during structural changes. The protection project remains named `ScreenshotShield`.
- Keep production builds independent of sibling source directories. Cross-project tests may use explicitly selected companion APKs.

## Development and verification

- Check the target project's framework and scope rules before choosing an implementation. Additional capabilities may use Vector/Xposed, SukiSU/KernelSU, or another mechanism.
- Add a matching detector or verification method when adding a restriction. Compare unprotected, protected, and ordinary-operation behavior with the permissions required for that path.
- Separate actual system events from constructed test content. Missing permissions or absent platform signals do not prove protection.
- Build the affected project independently. Update cross-project script paths and documentation when moving files.
- Existing emulator tools live in `module-screenshot-probe/scripts/` and accept only emulator serials. Use an explicitly authorized device for real-device work; preserve unrelated scope, service settings, clipboard contents, and notifications.
- Keep private data, keys, cookies, raw notification bodies, clipboard contents, and account identifiers out of logs and tracked files. Preserve the established signing state outside the workspace.

## Shared tooling

`scripts/build-all.sh` builds each independent Android project. `scripts/sign-apk.py` signs an explicitly selected APK using the established external key. Project-specific READMEs describe installation and test commands.
