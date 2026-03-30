#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
BUILD_ROOT_DEFAULT="$ROOT_DIR/build/rpmbuild/BUILD"
SYSTEM_LIBSTDCXX_DEFAULT="/usr/lib64/libstdc++.so.6"
BOOTSTRAP_ROOT_DEFAULT="$ROOT_DIR/build/bootstrap-root/opt/rh/devtoolset-14/root/usr"

usage() {
  cat <<'EOF'
Usage: check_libstdcxx_nonshared_build.sh [options]

Incrementally rebuild the EL7 libstdc++ nonshared convenience libraries in an
existing GCC build tree, then run the same compatibility link check that the
RPM build performs near the end of %build.

Options:
  --build-dir PATH        Prepared GCC source tree under build/rpmbuild/BUILD/gcc-*
  --stage auto|final|prev Which obj tree to use. Default: auto
  --refresh-overlay       Sync generated EL7 overlay sources into the prepared source tree
  --jobs N                Parallelism for make. Default: detected CPU count
  --system-libstdcxx PATH System libstdc++.so.6 used for the compatibility link
  --bootstrap-root PATH   Tool/runtime prefix used by the staged devtoolset-14 binutils
  -h, --help              Show this help text
EOF
}

fail() {
  echo "$*" >&2
  exit 1
}

detect_jobs() {
  getconf _NPROCESSORS_ONLN 2>/dev/null || echo 1
}

detect_build_dir() {
  find "$BUILD_ROOT_DEFAULT" -maxdepth 1 -mindepth 1 -type d -name 'gcc-*' | sort | tail -n 1
}

pick_stage_dir() {
  local obj_root=$1
  local stage=$2
  case "$stage" in
    auto)
      if [[ -d "$obj_root/x86_64-redhat-linux/libstdc++-v3/src" ]]; then
        echo "x86_64-redhat-linux"
      elif [[ -d "$obj_root/prev-x86_64-redhat-linux/libstdc++-v3/src" ]]; then
        echo "prev-x86_64-redhat-linux"
      else
        return 1
      fi
      ;;
    final)
      [[ -d "$obj_root/x86_64-redhat-linux/libstdc++-v3/src" ]] || return 1
      echo "x86_64-redhat-linux"
      ;;
    prev)
      [[ -d "$obj_root/prev-x86_64-redhat-linux/libstdc++-v3/src" ]] || return 1
      echo "prev-x86_64-redhat-linux"
      ;;
    *)
      return 1
      ;;
  esac
}

BUILD_DIR=""
STAGE="auto"
REFRESH_OVERLAY=0
JOBS=$(detect_jobs)
SYSTEM_LIBSTDCXX="$SYSTEM_LIBSTDCXX_DEFAULT"
BOOTSTRAP_ROOT="$BOOTSTRAP_ROOT_DEFAULT"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --build-dir)
      BUILD_DIR=${2:?missing value for --build-dir}
      shift 2
      ;;
    --stage)
      STAGE=${2:?missing value for --stage}
      shift 2
      ;;
    --refresh-overlay)
      REFRESH_OVERLAY=1
      shift
      ;;
    --jobs)
      JOBS=${2:?missing value for --jobs}
      shift 2
      ;;
    --system-libstdcxx)
      SYSTEM_LIBSTDCXX=${2:?missing value for --system-libstdcxx}
      shift 2
      ;;
    --bootstrap-root)
      BOOTSTRAP_ROOT=${2:?missing value for --bootstrap-root}
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "unknown option: $1"
      ;;
  esac
done

BUILD_DIR=${BUILD_DIR:-$(detect_build_dir)}
[[ -n "$BUILD_DIR" ]] || fail "no prepared gcc build tree found under $BUILD_ROOT_DEFAULT"
[[ -d "$BUILD_DIR" ]] || fail "build directory not found: $BUILD_DIR"
[[ -f "$SYSTEM_LIBSTDCXX" ]] || fail "system libstdc++ not found: $SYSTEM_LIBSTDCXX"

OBJ_ROOT="$BUILD_DIR/obj-x86_64-redhat-linux"
[[ -d "$OBJ_ROOT" ]] || fail "obj root not found: $OBJ_ROOT"

STAGE_DIR=$(pick_stage_dir "$OBJ_ROOT" "$STAGE") || fail "unable to resolve stage '$STAGE' under $OBJ_ROOT"
TARGET_ROOT="$OBJ_ROOT/$STAGE_DIR"
SRC_ROOT="$TARGET_ROOT/libstdc++-v3/src"
XGCC="$OBJ_ROOT/gcc/xgcc"
ARCHIVE="$SRC_ROOT/.libs/libstdc++_nonshared48.a"
OUTPUT_DIR="$ROOT_DIR/build/quick-check/$STAGE_DIR"
LOG_FILE="$OUTPUT_DIR/check.log"

mkdir -p "$OUTPUT_DIR"

cleanup() {
  local status=$?
  if [[ $status -eq 0 ]]; then
    echo "quick libstdc++ check passed; log: $LOG_FILE"
  else
    echo "quick libstdc++ check failed; log: $LOG_FILE" >&2
  fi
}
trap cleanup EXIT

exec > >(tee "$LOG_FILE") 2>&1

echo "Build tree: $BUILD_DIR"
echo "Stage dir:  $STAGE_DIR"
echo "Jobs:       $JOBS"
echo "System ABI: $SYSTEM_LIBSTDCXX"

[[ -x "$XGCC" ]] || fail "xgcc not found: $XGCC"
[[ -d "$SRC_ROOT" ]] || fail "libstdc++ build dir not found: $SRC_ROOT"

if [[ -d "$BOOTSTRAP_ROOT" ]]; then
  export PATH="$BOOTSTRAP_ROOT/bin:$PATH"
  export LD_LIBRARY_PATH="$BOOTSTRAP_ROOT/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  echo "Bootstrap:  $BOOTSTRAP_ROOT"
else
  echo "Bootstrap:  not found, using ambient PATH/LD_LIBRARY_PATH"
fi

if [[ $REFRESH_OVERLAY -eq 1 ]]; then
  echo "==> Syncing generated EL7 overlay sources into $BUILD_DIR"
  sync_output=$(
    python3 "$ROOT_DIR/scripts/generate_gcc14_el7_libstdcxx_compat_patch.py" \
    --sync-tree "$BUILD_DIR" \
    --sync-build-system \
    --skip-output
  )
  echo "$sync_output"
fi

invalidate_overlay_objects() {
  local base=$1
  local top_src=$2
  local file
  for file in \
    "$base/nonshared98/locale_facets.lo" \
    "$base/nonshared98/locale_facets.o" \
    "$base/nonshared98/locale-inst.lo" \
    "$base/nonshared98/locale-inst.o" \
    "$base/nonshared98/wlocale-inst.lo" \
    "$base/nonshared98/wlocale-inst.o" \
    "$base/nonshared98/.libs/libnonshared98convenience48.a" \
    "$base/nonshared98/libnonshared98convenience48.la" \
    "$base/nonshared11/codecvt.lo" \
    "$base/nonshared11/codecvt.o" \
    "$base/nonshared11/condition_variable.lo" \
    "$base/nonshared11/condition_variable.o" \
    "$base/nonshared11/cxx11-ios_failure.lo" \
    "$base/nonshared11/cxx11-ios_failure.o" \
    "$base/nonshared11/future48.lo" \
    "$base/nonshared11/future48.o" \
    "$base/nonshared11/random48.lo" \
    "$base/nonshared11/random48.o" \
    "$base/nonshared11/shared_ptr48.lo" \
    "$base/nonshared11/shared_ptr48.o" \
    "$base/nonshared11/thread48.lo" \
    "$base/nonshared11/thread48.o" \
    "$base/nonshared11/.libs/libnonshared11convenience48.a" \
    "$base/nonshared11/libnonshared11convenience48.la" \
    "$base/nonshared17/fs_ops.lo" \
    "$base/nonshared17/fs_ops.o" \
    "$base/nonshared17/fs_dir.lo" \
    "$base/nonshared17/fs_dir.o" \
    "$base/nonshared17/fs_path.lo" \
    "$base/nonshared17/fs_path.o" \
    "$base/nonshared17/.libs/libnonshared17convenience48.a" \
    "$base/nonshared17/libnonshared17convenience48.la" \
    "$base/nonshared20/tzdb80.lo" \
    "$base/nonshared20/tzdb80.o" \
    "$base/nonshared20/.libs/libnonshared20convenience48.a" \
    "$base/nonshared20/libnonshared20convenience48.la" \
    "$top_src/.libs/libstdc++_nonshared48.a" \
    "$top_src/libstdc++_nonshared48.la"; do
    rm -f "$file"
  done
}

run_make() {
  local dir=$1
  local target=$2
  echo "==> make -j$JOBS -C $dir $target"
  make -j "$JOBS" -C "$dir" V=1 "$target"
}

if [[ $REFRESH_OVERLAY -eq 1 ]]; then
  echo "==> Invalidating overlay-dependent nonshared objects"
  invalidate_overlay_objects "$SRC_ROOT" "$SRC_ROOT"
fi

run_make "$SRC_ROOT/nonshared98" libnonshared98convenience48.la
run_make "$SRC_ROOT/nonshared11" libnonshared11convenience48.la
run_make "$SRC_ROOT/nonshared17" libnonshared17convenience48.la
run_make "$SRC_ROOT/nonshared20" libnonshared20convenience48.la
run_make "$SRC_ROOT" libstdc++_nonshared48.la

[[ -f "$ARCHIVE" ]] || fail "nonshared archive not found: $ARCHIVE"

OUTPUT_SO="$OUTPUT_DIR/libstdc++_nonshared.so"
rm -f "$OUTPUT_SO"

echo "==> Linking compatibility DSO"
"$XGCC" -B "$OBJ_ROOT/gcc/" \
  -shared \
  -o "$OUTPUT_SO" \
  -Wl,--whole-archive "$ARCHIVE" \
  -Wl,--no-whole-archive "$SYSTEM_LIBSTDCXX"

echo "==> Running runtime relocation check"
ldd -d -r "$OUTPUT_SO" || :

SMOKE_SRC="$OUTPUT_DIR/locale_asan_smoke.cc"
SMOKE_OBJ="$OUTPUT_DIR/locale_asan_smoke.o"
SMOKE_BIN="$OUTPUT_DIR/locale_asan_smoke"
CXX_BIN="/opt/rh/devtoolset-11/root/usr/bin/g++"
CC_BIN="/opt/rh/devtoolset-11/root/usr/bin/gcc"
if [[ ! -x "$CXX_BIN" ]]; then
  CXX_BIN=$(command -v g++)
fi
if [[ ! -x "$CC_BIN" ]]; then
  CC_BIN=$(command -v gcc)
fi
[[ -n "$CXX_BIN" ]] || fail "g++ not found for smoke link"
[[ -n "$CC_BIN" ]] || fail "gcc not found for smoke link"

cat > "$SMOKE_SRC" <<'EOF_SMOKE'
#include <ctime>
#include <iomanip>
#include <locale>
#include <sstream>
#include <string>

int main() {
  std::locale loc = std::locale::classic();
  std::stringstream ss("1234");
  ss.imbue(loc);
  long value = 0;
  ss >> value;

  std::wstringstream ws(L"2024-03-28");
  ws.imbue(loc);
  std::tm tm = {};
  ws >> std::get_time(&tm, L"%Y-%m-%d");

  return (value == 1234 && !ws.fail()) ? 0 : 1;
}
EOF_SMOKE

echo "==> Building ASan locale smoke test"
"$CXX_BIN" -std=gnu++17 -O0 -g -c "$SMOKE_SRC" -o "$SMOKE_OBJ"
"$CC_BIN" -fsanitize=address "$SMOKE_OBJ" \
  -Wl,--start-group "$ARCHIVE" "$SYSTEM_LIBSTDCXX" -Wl,--end-group \
  -lm -lpthread -ldl -o "$SMOKE_BIN"

echo "Output: $OUTPUT_SO"
