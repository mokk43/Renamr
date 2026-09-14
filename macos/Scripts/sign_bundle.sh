#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_sign_helpers.sh"

bundle=""
identity=""
app_entitlements=""
service_entitlements=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bundle)
      bundle="$2"
      shift 2
      ;;
    --identity)
      identity="$2"
      shift 2
      ;;
    --app-entitlements)
      app_entitlements="$2"
      shift 2
      ;;
    --service-entitlements)
      service_entitlements="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "${bundle}" || -z "${identity}" ]]; then
  echo "Usage: $0 --bundle <Renamr.app> --identity <Developer ID ...>" >&2
  exit 1
fi

if [[ -z "${app_entitlements}" ]]; then
  app_entitlements="${SCRIPT_DIR}/../Renamr/Renamr.entitlements"
fi
if [[ -z "${service_entitlements}" ]]; then
  service_entitlements="${SCRIPT_DIR}/../RenamrPythonService/RenamrPythonService.entitlements"
fi

use_sandbox_entitlements=true
if [[ "${identity}" == "-" ]]; then
  use_sandbox_entitlements=false
  echo "Ad-hoc signing selected, sandbox entitlements will be skipped."
fi

service_bundle="${bundle}/Contents/XPCServices/RenamrPythonService.xpc"
service_resources="${service_bundle}/Contents/Resources"
sparkle_framework="${bundle}/Contents/Frameworks/Sparkle.framework"
python_framework="$(find "${service_bundle}" -type d -name "Python.framework" -print -quit)"

if [[ ! -d "${service_bundle}" ]]; then
  echo "Missing service bundle at ${service_bundle}" >&2
  exit 1
fi

echo "Signing embedded Python extensions"
sign_glob "${service_resources}" "*.so" "${identity}"
sign_glob "${service_resources}" "*.dylib" "${identity}"

if [[ -n "${python_framework}" ]]; then
  echo "Signing Python.framework binaries"
  if [[ -f "${python_framework}/Versions/Current/bin/python3" ]]; then
    sign_one "${python_framework}/Versions/Current/bin/python3" "${identity}"
  fi
  if [[ -f "${python_framework}/Versions/Current/Python" ]]; then
    sign_one "${python_framework}/Versions/Current/Python" "${identity}"
  fi
  sign_one "${python_framework}" "${identity}"
fi

runtime_launcher="${service_resources}/python/bin/python3"
if [[ -f "${runtime_launcher}" ]]; then
  sign_one "${runtime_launcher}" "${identity}"
fi

echo "Signing XPC service"
if [[ "${use_sandbox_entitlements}" == true ]]; then
  sign_one "${service_bundle}" "${identity}" "${service_entitlements}"
else
  sign_one "${service_bundle}" "${identity}"
fi

if [[ -d "${sparkle_framework}" ]]; then
  echo "Signing Sparkle helpers with preserved entitlements"
  while IFS= read -r -d '' helper; do
    if [[ "${identity}" == "-" ]]; then
      sign_one "${helper}" "${identity}"
    else
      tmp_entitlements="$(mktemp)"
      if codesign -d --entitlements :- "${helper}" > "${tmp_entitlements}" 2>/dev/null; then
        sign_one "${helper}" "${identity}" "${tmp_entitlements}"
      else
        sign_one "${helper}" "${identity}"
      fi
      rm -f "${tmp_entitlements}"
    fi
  done < <(find "${sparkle_framework}/Versions" -type f -perm -u+x -print0)
  while IFS= read -r -d '' nested_bundle; do
    sign_one "${nested_bundle}" "${identity}"
  done < <(find "${sparkle_framework}/Versions" -type d \( -name "Updater.app" -o -name "*.xpc" \) -print0)
  sign_one "${sparkle_framework}" "${identity}"
fi

echo "Signing outer app bundle"
if [[ "${use_sandbox_entitlements}" == true ]]; then
  sign_one "${bundle}" "${identity}" "${app_entitlements}"
else
  sign_one "${bundle}" "${identity}"
fi

echo "Verifying signature"
if [[ "${identity}" == "-" ]]; then
  codesign --verify --strict --verbose=2 "${bundle}"
else
  codesign --verify --strict --deep --verbose=2 "${bundle}"
  spctl --assess --type execute --verbose=4 "${bundle}" || true
fi
