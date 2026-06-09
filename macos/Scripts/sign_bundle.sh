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

service_bundle="${bundle}/Contents/XPCServices/RenamrPythonService.xpc"
service_resources="${service_bundle}/Contents/Resources"
sparkle_framework="${bundle}/Contents/Frameworks/Sparkle.framework"
python_framework="$(find "${service_bundle}" -type d -name "Python.framework" | head -n 1)"

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

echo "Signing XPC service"
sign_one "${service_bundle}" "${identity}" "${service_entitlements}"

if [[ -d "${sparkle_framework}" ]]; then
  echo "Signing Sparkle helpers with preserved entitlements"
  while IFS= read -r -d '' helper; do
    tmp_entitlements="$(mktemp)"
    if codesign -d --entitlements - "${helper}" > "${tmp_entitlements}" 2>/dev/null; then
      sign_one "${helper}" "${identity}" "${tmp_entitlements}"
    else
      sign_one "${helper}" "${identity}"
    fi
    rm -f "${tmp_entitlements}"
  done < <(find "${sparkle_framework}/Versions" -type f -perm -u+x -print0)
  sign_one "${sparkle_framework}" "${identity}"
fi

echo "Signing outer app bundle"
sign_one "${bundle}" "${identity}" "${app_entitlements}"

echo "Verifying signature"
codesign --verify --strict --deep --verbose=2 "${bundle}"
spctl --assess --type execute --verbose=4 "${bundle}" || true
