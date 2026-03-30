#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
EXTRACT_DIR=${1:-"$ROOT_DIR/vendor/extracted"}
OUT_DIR=${2:-"$ROOT_DIR/build/generated/SPECS"}
EXTRA_EXTRACT_DIR=${3:-"$ROOT_DIR/vendor/extracted-extra"}

mkdir -p "$OUT_DIR"

SEARCH_DIRS=()
for dir in "$EXTRACT_DIR" "$EXTRA_EXTRACT_DIR"; do
  if [[ -d "$dir" ]]; then
    SEARCH_DIRS+=("$dir")
  fi
done

rewrite_one() {
  local kind=$1
  local spec_path=$2
  local output_name=$3

  python3 "$ROOT_DIR/scripts/rewrite_scl_spec.py" \
    --kind "$kind" \
    --input "$spec_path" \
    --output "$OUT_DIR/$output_name"
}

find_first_spec() {
  local dir pattern found
  for dir in "${SEARCH_DIRS[@]}"; do
    for pattern in "$@"; do
      found=$(find "$dir" -type f -name "$pattern" | sort | head -n 1)
      if [[ -n "$found" ]]; then
        printf '%s\n' "$found"
        return 0
      fi
    done
  done
  return 0
}

gcc_spec=$(find_first_spec "*gcc-toolset-14-gcc*.spec" "gcc.spec")
binutils_spec=$(find_first_spec "*gcc-toolset-14-binutils*.spec" "binutils.spec")
gdb_spec=$(find_first_spec "*gcc-toolset-14-gdb*.spec" "gdb.spec")
annobin_spec=$(find_first_spec "*gcc-toolset-14-annobin*.spec" "annobin.spec")
dwz_spec=$(find_first_spec "*gcc-toolset-14-dwz*.spec" "dwz.spec")
make_spec=$(find_first_spec "*devtoolset-11-make*.spec" "make.spec")
elfutils_spec=$(find_first_spec "*devtoolset-11-elfutils*.spec" "elfutils.spec")

if [[ -n "$gcc_spec" ]]; then
  rewrite_one gcc "$gcc_spec" "devtoolset-14-gcc.spec"
fi
if [[ -n "$binutils_spec" ]]; then
  rewrite_one binutils "$binutils_spec" "devtoolset-14-binutils.spec"
fi
if [[ -n "$gdb_spec" ]]; then
  rewrite_one gdb "$gdb_spec" "devtoolset-14-gdb.spec"
fi
if [[ -n "$annobin_spec" ]]; then
  rewrite_one generic "$annobin_spec" "devtoolset-14-annobin.spec"
fi
if [[ -n "$dwz_spec" ]]; then
  rewrite_one generic "$dwz_spec" "devtoolset-14-dwz.spec"
fi
if [[ -n "$make_spec" ]]; then
  rewrite_one make "$make_spec" "devtoolset-14-make.spec"
fi
if [[ -n "$elfutils_spec" ]]; then
  rewrite_one elfutils "$elfutils_spec" "devtoolset-14-elfutils.spec"
fi
