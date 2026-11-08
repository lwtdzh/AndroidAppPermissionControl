#!/usr/bin/env python3
"""Sign a release APK with a persistent local key kept outside the source tree."""
import argparse
import os
import pathlib
import secrets
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("input", type=pathlib.Path)
parser.add_argument("output", type=pathlib.Path)
args = parser.parse_args()
sdk = pathlib.Path(os.environ.get("ANDROID_HOME", "/opt/homebrew/share/android-commandlinetools"))
state = pathlib.Path.home() / "Library/Application Support/ScreenshotShield/signing"
state.mkdir(parents=True, exist_ok=True, mode=0o700)
password_file = state / "keystore-password"
keystore = state / "release.p12"
if not password_file.exists():
    descriptor = os.open(password_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(secrets.token_urlsafe(32))
environment = dict(os.environ)
environment["SCREENSHOT_SHIELD_KEYSTORE_PASSWORD"] = password_file.read_text()
java = pathlib.Path(os.environ.get("JAVA_HOME", "/opt/homebrew/opt/openjdk@17")) / "bin"
if not keystore.exists():
    subprocess.run([
        str(java / "keytool"), "-genkeypair", "-keystore", str(keystore),
        "-storetype", "PKCS12", "-alias", "screenshotshield", "-keyalg", "RSA",
        "-keysize", "3072", "-validity", "10000", "-dname", "CN=ScreenshotShield",
        "-storepass:env", "SCREENSHOT_SHIELD_KEYSTORE_PASSWORD",
        "-keypass:env", "SCREENSHOT_SHIELD_KEYSTORE_PASSWORD",
    ], env=environment, check=True)
    keystore.chmod(0o600)
tool = sdk / "build-tools/36.0.0/apksigner"
subprocess.run([
    str(tool), "sign", "--ks", str(keystore), "--ks-key-alias", "screenshotshield",
    "--ks-pass", "env:SCREENSHOT_SHIELD_KEYSTORE_PASSWORD",
    "--out", str(args.output), str(args.input),
], env=environment, check=True)
subprocess.run([str(tool), "verify", "--verbose", str(args.output)], env=environment, check=True)
print("Signed APK: " + str(args.output))
