#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_ROOT="$(dirname "$(dirname "$(realpath "$0")")")"
export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@17}"
export ANDROID_HOME="${ANDROID_HOME:-/opt/homebrew/share/android-commandlinetools}"
exec "$WORKSPACE_ROOT/gradlew" -p "$WORKSPACE_ROOT" \
    :app:assembleRelease :verifier:assemblePrimaryRelease \
    :verifier:assembleSampleADebug :verifier:assembleSampleBDebug "$@" --console=plain
