#!/usr/bin/env bash

set -uo pipefail

BASE_PATH="${1:-../2026/pandora-2026-submissions}"
THREADS="${THREADS:-8}"

process_repo() {
    repo_dir="$1"
    repo="$(basename "$repo_dir")"

    error=$(
        (
            cd "$repo_dir" &&
            git reset --hard -q &&
            git clean -f -d -q &&
            git pull -q &&
            mvn -q clean package
        ) 2>&1
    )

    if [ $? -eq 0 ]; then
        echo "$repo 🟢"
    else
        echo "$repo 🔴 $error"
    fi
}

while IFS= read -r -d '' pom; do
    repo_dir="$(dirname "$pom")"

    process_repo "$repo_dir" &

    while [ "$(jobs -rp | wc -l)" -ge "$THREADS" ]; do
        sleep 0.2
    done

done < <(find "$BASE_PATH" -name pom.xml -print0)

wait