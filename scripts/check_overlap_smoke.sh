#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TOOLSET=${1:-devtoolset-14}
LEGACY_TOOLSET=${2:-devtoolset-11}
OUT_DIR="$ROOT_DIR/build/overlap-smoke/$TOOLSET"
SYSTEM_LIBSTDCXX=${SYSTEM_LIBSTDCXX:-/usr/lib64/libstdc++.so.6}
NONSHARED_ARCHIVE_OVERRIDE=${NONSHARED_ARCHIVE_OVERRIDE:-}
EXTRA_CXXFLAGS=${EXTRA_CXXFLAGS:-}

fail() {
  echo "$*" >&2
  exit 1
}

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

COMMON_LINK_FLAGS=()
COMMON_CXX_FLAGS=()

if [[ -n "$EXTRA_CXXFLAGS" ]]; then
  read -r -a COMMON_CXX_FLAGS <<<"$EXTRA_CXXFLAGS"
fi

if [[ -n "$NONSHARED_ARCHIVE_OVERRIDE" ]]; then
  [[ -f "$SYSTEM_LIBSTDCXX" ]] || fail "system libstdc++ not found: $SYSTEM_LIBSTDCXX"
  [[ -f "$NONSHARED_ARCHIVE_OVERRIDE" ]] || fail "override nonshared archive not found: $NONSHARED_ARCHIVE_OVERRIDE"

  mkdir -p "$OUT_DIR/libstdcxx-override"
  cat >"$OUT_DIR/libstdcxx-override/libstdc++.so" <<EOF
INPUT ( $SYSTEM_LIBSTDCXX $NONSHARED_ARCHIVE_OVERRIDE )
EOF
  COMMON_LINK_FLAGS=(-L"$OUT_DIR/libstdcxx-override")
fi

have_toolset() {
  local toolset=$1
  scl enable "$toolset" -- g++ --version >/dev/null 2>&1
}

run_toolset() {
  local toolset=$1
  shift
  scl enable "$toolset" -- "$@"
}

run_binary() {
  local name=$1
  local binary=$2
  local log="$OUT_DIR/$name.log"

  "$binary" >"$log" 2>&1 || {
    cat "$log" >&2
    fail "$name failed"
  }

  grep -q "OK $name" "$log" || {
    cat "$log" >&2
    fail "$name output missing success marker"
  }
}

compile_and_run_case() {
  local name=$1
  local source=$2
  shift 2
  local -a extra_flags=("$@")
  local binary="$OUT_DIR/$name"
  local -a cmd=(
    g++
    -std=gnu++17
    -O0
    -g
  )
  if [[ ${#COMMON_CXX_FLAGS[@]} -gt 0 ]]; then
    cmd+=("${COMMON_CXX_FLAGS[@]}")
  fi
  cmd+=("$source" -o "$binary")

  if [[ ${#COMMON_LINK_FLAGS[@]} -gt 0 ]]; then
    cmd+=("${COMMON_LINK_FLAGS[@]}")
  fi
  if [[ ${#extra_flags[@]} -gt 0 ]]; then
    cmd+=("${extra_flags[@]}")
  fi

  run_toolset "$TOOLSET" "${cmd[@]}"
  run_binary "$name" "$binary"

  cmd=(
    g++
    -std=gnu++17
    -O0
    -g
    -fsanitize=address
  )
  if [[ ${#COMMON_CXX_FLAGS[@]} -gt 0 ]]; then
    cmd+=("${COMMON_CXX_FLAGS[@]}")
  fi
  cmd+=("$source" -o "$binary.asan")
  if [[ ${#COMMON_LINK_FLAGS[@]} -gt 0 ]]; then
    cmd+=("${COMMON_LINK_FLAGS[@]}")
  fi
  if [[ ${#extra_flags[@]} -gt 0 ]]; then
    cmd+=("${extra_flags[@]}")
  fi

  run_toolset "$TOOLSET" "${cmd[@]}"
  run_binary "$name" "$binary.asan"
}

compile_and_run_mixed_abi_case() {
  local name=legacy_overlap_main
  local provider_src="$ROOT_DIR/tests/overlap/legacy_overlap_provider.cpp"
  local main_src="$ROOT_DIR/tests/overlap/legacy_overlap_main.cpp"
  local provider_obj="$OUT_DIR/legacy_overlap_provider.o"
  local provider_lib="$OUT_DIR/liblegacy_overlap.a"

  if ! have_toolset "$LEGACY_TOOLSET"; then
    echo "Skipping mixed ABI smoke: $LEGACY_TOOLSET is not installed"
    return 0
  fi

  run_toolset "$LEGACY_TOOLSET" \
    g++ -std=gnu++17 -O0 -g -c "$provider_src" -o "$provider_obj" -pthread
  ar rcs "$provider_lib" "$provider_obj"

  local -a cmd=(
    g++
    -std=gnu++17
    -O0
    -g
  )
  if [[ ${#COMMON_CXX_FLAGS[@]} -gt 0 ]]; then
    cmd+=("${COMMON_CXX_FLAGS[@]}")
  fi
  cmd+=("$main_src" "$provider_lib" -o "$OUT_DIR/$name" -pthread)
  if [[ ${#COMMON_LINK_FLAGS[@]} -gt 0 ]]; then
    cmd+=("${COMMON_LINK_FLAGS[@]}")
  fi
  run_toolset "$TOOLSET" "${cmd[@]}"
  run_binary "$name" "$OUT_DIR/$name"

  cmd=(
    g++
    -std=gnu++17
    -O0
    -g
    -fsanitize=address
  )
  if [[ ${#COMMON_CXX_FLAGS[@]} -gt 0 ]]; then
    cmd+=("${COMMON_CXX_FLAGS[@]}")
  fi
  cmd+=("$main_src" "$provider_lib" -o "$OUT_DIR/$name.asan" -pthread)
  if [[ ${#COMMON_LINK_FLAGS[@]} -gt 0 ]]; then
    cmd+=("${COMMON_LINK_FLAGS[@]}")
  fi
  run_toolset "$TOOLSET" "${cmd[@]}"
  run_binary "$name" "$OUT_DIR/$name.asan"
}

have_toolset "$TOOLSET" || fail "toolset '$TOOLSET' is not installed"

compile_and_run_case \
  ios_failure \
  "$ROOT_DIR/tests/overlap/ios_failure.cpp"

compile_and_run_case \
  regex_error \
  "$ROOT_DIR/tests/overlap/regex_error.cpp"

compile_and_run_case \
  locale_time_get \
  "$ROOT_DIR/tests/overlap/locale_time_get.cpp"

compile_and_run_case \
  future_error \
  "$ROOT_DIR/tests/overlap/future_error.cpp"

compile_and_run_case \
  thread_condition_variable \
  "$ROOT_DIR/tests/overlap/thread_condition_variable.cpp" \
  -pthread

compile_and_run_mixed_abi_case

echo "Overlap smoke tests passed under $TOOLSET"
