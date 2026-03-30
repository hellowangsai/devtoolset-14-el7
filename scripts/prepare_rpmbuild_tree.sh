#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
EXTRACT_DIR=${1:-"$ROOT_DIR/vendor/extracted-core"}
GENERATED_CORE_SPECS=${2:-"$ROOT_DIR/build/generated/CORE_SPECS"}
GENERATED_META_SPECS=${3:-"$ROOT_DIR/build/generated/SPECS"}
RPMBUILD_ROOT=${4:-"$ROOT_DIR/build/rpmbuild"}
GENERATED_PATCHES_DIR=${5:-"$ROOT_DIR/build/generated/PATCHES"}

mkdir -p \
  "$RPMBUILD_ROOT/BUILD" \
  "$RPMBUILD_ROOT/BUILDROOT" \
  "$RPMBUILD_ROOT/RPMS" \
  "$RPMBUILD_ROOT/SOURCES" \
  "$RPMBUILD_ROOT/SPECS" \
  "$RPMBUILD_ROOT/SRPMS"

mkdir -p "$GENERATED_PATCHES_DIR"

copy_specs() {
  local source_dir=$1
  if [[ ! -d "$source_dir" ]]; then
    return 0
  fi

  local spec
  shopt -s nullglob
  for spec in "$source_dir"/*.spec; do
    cp -f "$spec" "$RPMBUILD_ROOT/SPECS/"
  done
}

copy_sources() {
  if [[ ! -d "$EXTRACT_DIR" ]]; then
    return 0
  fi

  local file
  while IFS= read -r -d '' file; do
    case "$file" in
      *.spec)
        ;;
      *)
        cp -f "$file" "$RPMBUILD_ROOT/SOURCES/"
        ;;
    esac
  done < <(find "$EXTRACT_DIR" -type f -print0)
}

copy_sources
copy_specs "$GENERATED_META_SPECS"
copy_specs "$GENERATED_CORE_SPECS"

python3 "$ROOT_DIR/scripts/generate_gcc14_el7_libstdcxx_compat_patch.py" \
  --output "$GENERATED_PATCHES_DIR/gcc14-libstdc++-compat-el7.patch"
cp -f \
  "$GENERATED_PATCHES_DIR/gcc14-libstdc++-compat-el7.patch" \
  "$RPMBUILD_ROOT/SOURCES/"

echo "Prepared rpmbuild tree at $RPMBUILD_ROOT"
