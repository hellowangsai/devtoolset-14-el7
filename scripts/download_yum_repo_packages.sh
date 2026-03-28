#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUT_DIR=${1:-"$ROOT_DIR/vendor/rpms"}
PACKAGES_FILE=${2:?packages file is required}
REPO_BASE_URL=${3:?repo base URL is required}
ARCH=${4:-}

mkdir -p "$OUT_DIR"

MANIFEST_JSON="$OUT_DIR/packages.json"
LINES_FILE=$(mktemp)
trap 'rm -f "$LINES_FILE"' EXIT

cmd=(
  python3 "$ROOT_DIR/scripts/discover_yum_repo_packages.py"
  --repo-base-url "$REPO_BASE_URL"
  --packages-file "$PACKAGES_FILE"
  --format lines
)
if [[ -n "$ARCH" ]]; then
  cmd+=(--arch "$ARCH")
fi
"${cmd[@]}" > "$LINES_FILE"

while IFS=$'\t' read -r package arch filename url; do
  if [[ -z "$package" ]]; then
    continue
  fi
  echo "Downloading $filename ($arch)"
  curl -fL --retry 3 -o "$OUT_DIR/$filename" "$url"
done < "$LINES_FILE"

cmd=(
  python3 "$ROOT_DIR/scripts/discover_yum_repo_packages.py"
  --repo-base-url "$REPO_BASE_URL"
  --packages-file "$PACKAGES_FILE"
  --pretty
)
if [[ -n "$ARCH" ]]; then
  cmd+=(--arch "$ARCH")
fi
"${cmd[@]}" > "$MANIFEST_JSON"

echo "Wrote manifest to $MANIFEST_JSON"
