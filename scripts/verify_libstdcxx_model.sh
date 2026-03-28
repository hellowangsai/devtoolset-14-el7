#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REFERENCE_TOOLSET=${1:-devtoolset-11}
SPEC_PATH=${2:-"$ROOT_DIR/build/generated/CORE_SPECS/devtoolset-14-gcc.spec"}
REFERENCE_ROOT="/opt/rh/$REFERENCE_TOOLSET/root/usr"

fail() {
  echo "$*" >&2
  exit 1
}

reference_script=$(
  find "$REFERENCE_ROOT/lib/gcc" -type f -name libstdc++.so \
    ! -path '*/32/*' ! -path '*/lib32/*' | sort | head -n 1
)
[[ -n "$reference_script" ]] || fail "missing reference libstdc++.so linker script under $REFERENCE_ROOT"

if find "$REFERENCE_ROOT/lib64" -maxdepth 1 -type f -name 'libstdc++.so.6*' | grep -q .; then
  fail "reference toolset $REFERENCE_TOOLSET unexpectedly ships a private libstdc++.so.6 in $REFERENCE_ROOT/lib64"
fi

python3 - "$reference_script" <<'PY' || fail "reference linker script does not match the expected system-libstdc++ model: $reference_script"
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text(encoding="utf-8")
if "/usr/lib64/libstdc++.so.6" not in text:
    raise SystemExit(1)
if "-lstdc++_nonshared" not in text:
    raise SystemExit(1)
PY

if [[ ! -f "$SPEC_PATH" ]]; then
  fail "generated gcc spec not found: $SPEC_PATH"
fi

parsed_spec=$(mktemp)
files_section=$(mktemp)
trap 'rm -f "$parsed_spec" "$files_section"' EXIT

rpmspec --parse "$SPEC_PATH" > "$parsed_spec"

if rg -n '/opt/rh/devtoolset-14/root/usr/lib64/libstdc\+\+\.so\.6' "$parsed_spec" >/dev/null; then
  fail "parsed gcc spec still references a private SCL libstdc++.so.6"
fi

rg -n 'INPUT \( /usr/lib64/libstdc\+\+\.so\.6 -lstdc\+\+_nonshared' "$parsed_spec" >/dev/null \
  || fail "parsed gcc spec does not generate the expected system-libstdc++ linker script"

sed -n '/^%files -n %{?scl_prefix}libstdc++.*-devel/,/^%if %{build_libstdcxx_docs}/p' "$SPEC_PATH" > "$files_section"

if rg -n 'libstdc\+\+\.so\.6' "$files_section" >/dev/null; then
  fail "libstdc++-devel files section must not package libstdc++.so.6"
fi

rg -n 'libstdc\+\+\.so$' "$files_section" >/dev/null \
  || fail "libstdc++-devel files section must ship the libstdc++.so linker script"

echo "libstdc++ model verification passed against $REFERENCE_TOOLSET and $(basename "$SPEC_PATH")"
