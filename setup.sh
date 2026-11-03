#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == concealment ]]; then
    shift
    exec python3 "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/tools/concealment.py" "$@"
fi
exec python3 "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/tools/setup.py" "$@"
