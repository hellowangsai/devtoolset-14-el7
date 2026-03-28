#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
SRPM_DIR=${1:-"$ROOT_DIR/vendor/srpms"}
OUT_DIR=${2:-"$ROOT_DIR/vendor/extracted"}

if ! command -v rpm2cpio >/dev/null 2>&1; then
  echo "rpm2cpio is required" >&2
  exit 1
fi

if ! command -v cpio >/dev/null 2>&1; then
  echo "cpio is required" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

shopt -s nullglob
for srpm in "$SRPM_DIR"/*.src.rpm; do
  srpm=$(readlink -f "$srpm")
  name=$(basename "$srpm" .src.rpm)
  target="$OUT_DIR/$name"
  rm -rf "$target"
  mkdir -p "$target"
  (
    cd "$target"
    rpm2cpio "$srpm" | cpio -idmu --quiet
  )
  echo "Extracted $name"
done
