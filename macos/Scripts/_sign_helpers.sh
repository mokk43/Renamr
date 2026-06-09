#!/usr/bin/env bash
set -euo pipefail

sign_one() {
  local path="$1"
  local identity="$2"
  local entitlements="${3:-}"

  if [[ -n "${entitlements}" ]]; then
    codesign --force --timestamp --options runtime --sign "${identity}" --entitlements "${entitlements}" "${path}"
  else
    codesign --force --timestamp --options runtime --sign "${identity}" "${path}"
  fi
}

sign_glob() {
  local base="$1"
  local pattern="$2"
  local identity="$3"
  while IFS= read -r -d '' entry; do
    sign_one "${entry}" "${identity}"
  done < <(find "${base}" -type f -name "${pattern}" -print0 | sort -z)
}
