#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
SPEC_PATH=${1:-"$ROOT_DIR/build/generated/CORE_SPECS/devtoolset-14-gcc.spec"}
shift || true

if [[ ! -f "$SPEC_PATH" ]]; then
  echo "missing spec: $SPEC_PATH" >&2
  exit 2
fi

status=0

while IFS= read -r req; do
  [[ -z "$req" ]] && continue
  if provider=$(rpm -q --whatprovides "$req" 2>/dev/null | head -n 1); then
    printf 'ok      %s -> %s\n' "$req" "$provider"
  else
    printf 'missing %s\n' "$req"
    status=1
  fi
done < <(rpmspec -q --buildrequires "$SPEC_PATH" "$@" | LC_ALL=C sort -u)

exit "$status"
