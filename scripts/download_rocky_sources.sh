#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUT_DIR=${1:-"$ROOT_DIR/vendor/srpms"}
COMPONENTS_FILE=${2:-"$ROOT_DIR/manifests/rocky8-core-components.txt"}

mkdir -p "$OUT_DIR"

MANIFEST_JSON="$OUT_DIR/sources.json"
LINES_FILE=$(mktemp)
trap 'rm -f "$LINES_FILE"' EXIT

python3 "$ROOT_DIR/scripts/discover_rocky_sources.py" \
  --components-file "$COMPONENTS_FILE" \
  --format lines > "$LINES_FILE"

while IFS=$'\t' read -r component filename url; do
  if [[ -z "$component" ]]; then
    continue
  fi
  echo "Downloading $filename"
  curl -fL --retry 3 -o "$OUT_DIR/$filename" "$url"
done < "$LINES_FILE"

python3 "$ROOT_DIR/scripts/discover_rocky_sources.py" \
  --components-file "$COMPONENTS_FILE" \
  --pretty > "$MANIFEST_JSON"

echo "Wrote manifest to $MANIFEST_JSON"
