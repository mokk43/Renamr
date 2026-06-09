#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DIST_DIR="${ROOT_DIR}/../dist"
IDENTITY=""
NOTARY_PROFILE=""
BUNDLE_PATH=""
SPARKLE_KEY_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --identity)
      IDENTITY="$2"
      shift 2
      ;;
    --notary-profile)
      NOTARY_PROFILE="$2"
      shift 2
      ;;
    --bundle)
      BUNDLE_PATH="$2"
      shift 2
      ;;
    --sparkle-key-file)
      SPARKLE_KEY_FILE="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "${IDENTITY}" || -z "${NOTARY_PROFILE}" ]]; then
  echo "Usage: $0 --identity <Developer ID ...> --notary-profile <profile> [--bundle <Renamr.app>]" >&2
  exit 1
fi

mkdir -p "${DIST_DIR}"

"${SCRIPT_DIR}/vendor_python.sh"

if [[ -z "${BUNDLE_PATH}" ]]; then
  echo "Building macOS release app bundle..."
  xcodebuild \
    -scheme Renamr \
    -configuration Release \
    -derivedDataPath "${ROOT_DIR}/build" \
    -destination "platform=macOS" \
    build
  BUNDLE_PATH="$(find "${ROOT_DIR}/build" -type d -name "Renamr.app" | head -n 1)"
fi

if [[ -z "${BUNDLE_PATH}" || ! -d "${BUNDLE_PATH}" ]]; then
  echo "Could not locate Renamr.app bundle." >&2
  exit 1
fi

"${SCRIPT_DIR}/prepare_python_runtime.sh" --bundle "${BUNDLE_PATH}" --repo-root "${ROOT_DIR}/.."

"${SCRIPT_DIR}/sign_bundle.sh" --bundle "${BUNDLE_PATH}" --identity "${IDENTITY}"
"${SCRIPT_DIR}/notarize.sh" --bundle "${BUNDLE_PATH}" --keychain-profile "${NOTARY_PROFILE}"

DMG_PATH="${DIST_DIR}/Renamr.dmg"
"${SCRIPT_DIR}/build_dmg.sh" --app "${BUNDLE_PATH}" --output "${DMG_PATH}" --volume-name "Renamr"

UPDATES_DIR="${DIST_DIR}/updates"
mkdir -p "${UPDATES_DIR}"
cp -f "${DMG_PATH}" "${UPDATES_DIR}/"
if [[ -n "${SPARKLE_KEY_FILE}" ]]; then
  "${SCRIPT_DIR}/generate_appcast.sh" --updates-dir "${UPDATES_DIR}" --key-file "${SPARKLE_KEY_FILE}"
else
  "${SCRIPT_DIR}/generate_appcast.sh" --updates-dir "${UPDATES_DIR}"
fi

size_bytes="$(stat -f%z "${DMG_PATH}")"
echo "release_dmg=${DMG_PATH}"
echo "release_size_bytes=${size_bytes}"
if [[ "${size_bytes}" -gt 83886080 ]]; then
  echo "warning: release artifact exceeds 80MB soft target" >&2
fi
