#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <binary-path> <output-plist>" >&2
  exit 1
fi

binary_path="$1"
output_path="$2"

codesign -d --entitlements - "${binary_path}" > "${output_path}" 2>/dev/null
