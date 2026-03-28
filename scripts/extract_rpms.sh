#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
RPM_DIR=${1:-"$ROOT_DIR/vendor/rpms"}
OUT_DIR=${2:-"$ROOT_DIR/vendor/extracted-rpms"}

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
count=0
for rpm in "$RPM_DIR"/*.rpm; do
  rpm=$(readlink -f "$rpm")
  name=$(basename "$rpm" .rpm)
  target="$OUT_DIR/$name"
  rm -rf "$target"
  mkdir -p "$target"
  (
    cd "$target"
    rpm2cpio "$rpm" | cpio -idmu --quiet
  )
  echo "Extracted $name"
  count=$((count + 1))
done

if [[ "$count" -eq 0 ]]; then
  echo "no RPMs found in $RPM_DIR" >&2
  exit 1
fi
