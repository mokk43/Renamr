#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VERSIONS_FILE="${ROOT_DIR}/VERSIONS"
VENDORED_DIR="${ROOT_DIR}/Vendored"
TMP_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

if [[ ! -f "${VERSIONS_FILE}" ]]; then
  echo "Missing ${VERSIONS_FILE}" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "${VERSIONS_FILE}"

if [[ -z "${PYTHON_APPLE_SUPPORT:-}" ]]; then
  echo "PYTHON_APPLE_SUPPORT is not set in ${VERSIONS_FILE}" >&2
  exit 1
fi

mkdir -p "${VENDORED_DIR}"
rm -rf \
  "${VENDORED_DIR}/Python.xcframework" \
  "${VENDORED_DIR}/python-stdlib" \
  "${VENDORED_DIR}/app_packages"
mkdir -p "${VENDORED_DIR}/app_packages"

echo "Resolving python-apple-support release ${PYTHON_APPLE_SUPPORT}..."
release_json="$(curl -fsSL "https://api.github.com/repos/beeware/Python-Apple-support/releases/tags/${PYTHON_APPLE_SUPPORT}")"

asset_url="$(python3 - <<'PY' "${release_json}"
import json
import sys

payload = json.loads(sys.argv[1])
assets = payload.get("assets", [])
for asset in assets:
    name = asset.get("name", "")
    if "macOS" in name and name.endswith(".tar.gz"):
        print(asset.get("browser_download_url", ""))
        sys.exit(0)
print("")
PY
)"

if [[ -z "${asset_url}" ]]; then
  echo "Could not find a macOS tarball in release ${PYTHON_APPLE_SUPPORT}" >&2
  exit 1
fi

echo "Downloading ${asset_url}"
curl -fL "${asset_url}" -o "${TMP_DIR}/python-apple-support.tar.gz"
tar -xzf "${TMP_DIR}/python-apple-support.tar.gz" -C "${TMP_DIR}"

xcframework_path="$(find "${TMP_DIR}" -type d -name "Python.xcframework" | head -n 1)"
stdlib_path="$(find "${TMP_DIR}" -type d -name "python-stdlib" | head -n 1)"

if [[ -z "${xcframework_path}" || -z "${stdlib_path}" ]]; then
  echo "Downloaded archive did not contain Python.xcframework/python-stdlib" >&2
  exit 1
fi

cp -R "${xcframework_path}" "${VENDORED_DIR}/Python.xcframework"
cp -R "${stdlib_path}" "${VENDORED_DIR}/python-stdlib"

echo "Installing wheels into ${VENDORED_DIR}/app_packages"
python3 -m pip install \
  --upgrade \
  --target "${VENDORED_DIR}/app_packages" \
  --only-binary=:all: \
  --platform macosx_11_0_universal2 \
  --python-version 3.13 \
  "lxml" \
  "httpx" \
  "openai" \
  "ebooklib" \
  "beautifulsoup4" \
  "charset-normalizer"

echo "Pruning vendor tree"
find "${VENDORED_DIR}" -type d \( -name tests -o -name test -o -name __pycache__ \) -prune -exec rm -rf {} +
find "${VENDORED_DIR}" -type f -path "*/.dist-info/RECORD" -delete
rm -rf \
  "${VENDORED_DIR}/python-stdlib/tkinter" \
  "${VENDORED_DIR}/python-stdlib/idlelib" \
  "${VENDORED_DIR}/python-stdlib/ensurepip" \
  "${VENDORED_DIR}/python-stdlib/pydoc_data"

echo "Vendor sizing report"
python3 - <<'PY' "${VENDORED_DIR}"
from pathlib import Path
import sys

root = Path(sys.argv[1])
total = 0
entries = []
for child in sorted(root.iterdir()):
    size = sum(p.stat().st_size for p in child.rglob("*") if p.is_file())
    total += size
    entries.append((child.name, size))

print(f"total_bytes={total}")
for name, size in entries:
    print(f"{name}={size}")
PY
