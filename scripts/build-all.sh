#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_ROOT="$(dirname "$(dirname "$(realpath "$0")")")"
projects=0
for project in "$WORKSPACE_ROOT"/module-*; do
    if [[ ! -d "$project" || ! -x "$project/gradlew" ]]; then
        continue
    fi
    printf 'Building %s\n' "$(basename "$project")"
    "$project/gradlew" -p "$project" "$@" --console=plain
    projects=$((projects + 1))
done

if [[ $projects -eq 0 ]]; then
    printf '%s\n' 'No independent Android projects with Gradle wrappers were found.' >&2
    exit 1
fi
printf 'Built %d independent Android projects.\n' "$projects"
