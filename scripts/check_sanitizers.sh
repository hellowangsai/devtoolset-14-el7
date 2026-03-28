#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TOOLSET=${1:-devtoolset-14}
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

compile_and_run() {
  local kind=$1
  local source=$2
  local binary=$3
  local expect=$4
  local allow_zero_exit=${5:-0}
  local log="$TMP_DIR/$kind.log"

  scl enable "$TOOLSET" -- \
    gcc -O0 -g "$source" "-fsanitize=$kind" -o "$binary"

  set +e
  "$binary" >"$log" 2>&1
  local rc=$?
  set -e

  if [[ $allow_zero_exit -ne 1 && $rc -eq 0 ]]; then
    echo "$kind test unexpectedly succeeded" >&2
    cat "$log" >&2
    exit 1
  fi
  if ! grep -q "$expect" "$log"; then
    echo "$kind output missing expected marker '$expect'" >&2
    cat "$log" >&2
    exit 1
  fi
}

compile_and_run \
  address \
  "$ROOT_DIR/tests/sanitizer/asan_heap_overflow.c" \
  "$TMP_DIR/asan-demo" \
  "AddressSanitizer"

compile_and_run \
  undefined \
  "$ROOT_DIR/tests/sanitizer/ubsan_signed_overflow.c" \
  "$TMP_DIR/ubsan-demo" \
  "runtime error" \
  1

echo "ASan and UBSan smoke tests passed under $TOOLSET"
