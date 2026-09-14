#!/usr/bin/env bash
set -euo pipefail

sign_one() {
  local path="$1"
  local identity="$2"
  local entitlements="${3:-}"
  local args=(--force --sign "${identity}")

  if [[ "${identity}" != "-" ]]; then
    args+=(--timestamp --options runtime)
  fi

  if [[ -n "${entitlements}" ]]; then
    codesign "${args[@]}" --entitlements "${entitlements}" "${path}"
  else
    codesign "${args[@]}" "${path}"
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
