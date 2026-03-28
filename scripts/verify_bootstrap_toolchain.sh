#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
BOOTSTRAP_TOOLSET=${1:-devtoolset-11}
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

cat > "$TMP_DIR/cxx17.cpp" <<'EOF'
#include <optional>
#include <string>

int main() {
    std::optional<std::string> value("ok");
    return value.has_value() ? 0 : 1;
}
EOF

scl enable "$BOOTSTRAP_TOOLSET" -- gcc --version | head -n 1
scl enable "$BOOTSTRAP_TOOLSET" -- g++ --version | head -n 1
scl enable "$BOOTSTRAP_TOOLSET" -- g++ -std=gnu++17 "$TMP_DIR/cxx17.cpp" -o "$TMP_DIR/cxx17"
"$TMP_DIR/cxx17"
scl enable "$BOOTSTRAP_TOOLSET" -- gcc -O0 -g -fsanitize=address -c \
  "$ROOT_DIR/tests/sanitizer/asan_heap_overflow.c" -o "$TMP_DIR/asan-demo.o"
scl enable "$BOOTSTRAP_TOOLSET" -- gcc -O0 -g -fsanitize=undefined -c \
  "$ROOT_DIR/tests/sanitizer/ubsan_signed_overflow.c" -o "$TMP_DIR/ubsan-demo.o"

echo "Bootstrap toolchain verification passed under $BOOTSTRAP_TOOLSET"
