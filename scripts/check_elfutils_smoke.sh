#!/usr/bin/env bash
set -euo pipefail

TOOLSET=${1:-devtoolset-14}
SCL_PREFIX=/opt/rh/${TOOLSET}
ENABLE_SCRIPT=${SCL_PREFIX}/enable

if [[ ! -f "${ENABLE_SCRIPT}" ]]; then
  echo "missing enable script: ${ENABLE_SCRIPT}" >&2
  exit 1
fi

tmpdir=$(mktemp -d)
cleanup() {
  rm -rf "${tmpdir}"
}
trap cleanup EXIT

cat > "${tmpdir}/hello.c" <<'EOF'
#include <stdio.h>
int main(void) { puts("ok"); return 0; }
EOF

source "${ENABLE_SCRIPT}"
hash -r

gcc -g -O2 "${tmpdir}/hello.c" -o "${tmpdir}/hello"

eu-readelf --version >/dev/null
eu-strip --version >/dev/null
eu-nm --version >/dev/null
eu-addr2line --version >/dev/null

eu-readelf -h "${tmpdir}/hello" >/dev/null
eu-readelf -S "${tmpdir}/hello" >/dev/null
eu-nm "${tmpdir}/hello" >/dev/null

cp "${tmpdir}/hello" "${tmpdir}/hello.strip"
eu-strip "${tmpdir}/hello.strip"

main_addr=$(nm "${tmpdir}/hello" | awk '/ main$/{print $1; exit}')
if [[ -z "${main_addr}" ]]; then
  echo "failed to find main symbol" >&2
  exit 1
fi
eu-addr2line -e "${tmpdir}/hello" "${main_addr}" >/dev/null

echo "elfutils smoke tests passed under ${TOOLSET}"
