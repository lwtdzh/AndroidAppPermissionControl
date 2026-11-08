# Project relationships

This is the shared record of relationships between subprojects in AndroidAppPermissionControl. Read the relevant group before changing a project, then check the companion projects and tools it names.

Whenever two or more subprojects are created with a relationship, add that relationship to this same file. Update the relevant section when projects are renamed, relationships change, or a change requires companion tools to be updated. Keep project-specific usage in each project's README and link back here.

## Screenshot protection and verification

### Roles

| Project | Role | Current version |
| --- | --- | --- |
| [module-screenshot-shield](module-screenshot-shield/README.md) | The Vector/Xposed module that blocks screenshot observation in selected app processes | `0.1.3` |
| [module-screenshot-detector](module-screenshot-detector/README.md) | A standalone app that displays screenshot signals and manual image-read checks before and after protection | `0.1.1` |
| [module-screenshot-probe](module-screenshot-probe/README.md) | A standalone app and emulator tools that verify protection and ordinary-operation controls | `0.1.0` |

The detector and probe are companion verification apps for the shield. They also run independently to establish an unprotected baseline. Their APKs are installed separately; when either app is selected in Vector scope, the shield is injected into that app's process.

Each project builds independently. Production Java/native source code and Gradle builds have no dependency on sibling projects. Their relationships are through framework injection, separately installed APKs, and cross-project test tools.

### What the projects use from one another

| Relationship | How it is used |
| --- | --- |
| Shield → detector | The shield suppresses observation inside the detector when that package is in Vector scope; the detector's UI shows whether the same signal remains visible |
| Shield → probe | The shield suppresses observation inside the probe; automated tests compare module-disabled, protected, and outside-scope results, including ordinary-operation controls |
| Probe tools → detector read tests | The probe integration runner creates indexed screenshot and ordinary-image fixtures that the detector's system-picker tests select |

The detector requires Android 14 or later. The shield and probe support installation from Android 8.1; probe tests of the Android screenshot callback require that API to exist. The probe intentionally targets SDK 28 for legacy storage checks. Existing automated runners use the dedicated Android 16 emulator with Vector.

### Shared test assumptions

- [Probe integration runner](module-screenshot-probe/scripts/emulator-test.py) installs the probe debug APK and a selected shield APK. Its default shield path is the sibling shield project's `app/build/outputs/apk/debug/app-debug.apk`; `--module-apk` selects another APK. Preserve compatibility with any already installed signing identity.
- [Official callback runner](module-screenshot-probe/scripts/official-callback-test.py) uses installed shield and probe APKs and a real SystemUI screenshot. It does not build or install those APKs itself.
- [Visible detector runner](module-screenshot-detector/scripts/detector-test.py) uses installed shield and detector APKs. It currently checks shield version `0.1.3` and detector version `0.1.1`; update its version checks and recorded expectations when changing either release.
- [Detector read runner](module-screenshot-detector/scripts/detector-read-test.py) uses fixtures created by the probe integration runner. It selects `Screenshot_probe.png` and `ordinary_probe.png` through the system picker, and imports helpers from its neighboring `detector-test.py`. Changes to fixture names or helper locations must be reflected in both producers and consumers.
- All runners identify packages by their application IDs. Package renames require reviewing companion-script constants, Vector scope entries, installation commands, and documentation.
- Notification and clipboard tests need the relevant access and foreground conditions. Zero signals caused by absent permissions or absent platform events do not prove shield behavior.

### Test order and evidence

1. Build the shield and the verification app needed for the affected path, using each project's own wrapper. Sign and install compatible APKs on the selected test device.
2. Use the probe integration runner for low-level hook and ordinary-operation checks. Run it before detector read checks when its image fixtures are needed.
3. Use the official callback runner for real SystemUI callback evidence, or the visible detector runner for its observation paths.
4. Use the detector read runner for system-granted image URI checks. Device-specific notification and clipboard checks must distinguish actual screenshot behavior from labeled test content.

Protection audits and historical hook results are in [the shield project](module-screenshot-shield/COVERAGE-AUDIT.md) and its [verification directory](module-screenshot-shield/verification/). Visible detector, URI-read, and vivo notification/clipboard results are in [detector verification](module-screenshot-detector/verification/). The relocated probe integration result is in [probe verification](module-screenshot-probe/verification/).

When changing a shield hook, review the corresponding detector route and probe assertions. When adding a detector or probe route, check whether the shield handles that entry point. Update only the affected implementations, tests, and shared assumptions; retain a readable unprotected baseline and ordinary-operation control.

## Recording future related projects

Add a section here for every new related group, including groups that use SukiSU/KernelSU or another framework. Record:

- The participating project directories and each project's role.
- Whether the relationship is a build dependency, runtime integration, verification relationship, shared service, or shared test data.
- What crosses the project boundary: APKs, package IDs, interfaces, files, events, configuration, or fixture names.
- Required installation order, framework scope, permissions, platform versions, and compatible versions where applicable.
- Which companion projects or tools need review when one side changes.
- Test order, ordinary-operation controls, and the locations of verification records.

Link each participating project's README to this file. Update the root project table when adding a project. Before finishing a change that affects a relationship, update its section here and verify the affected companion paths.
