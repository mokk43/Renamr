#!/usr/bin/env bash
set -euo pipefail

output_bundle=""
repo_root=""
configuration="release"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output)
      output_bundle="$2"
      shift 2
      ;;
    --repo-root)
      repo_root="$2"
      shift 2
      ;;
    --configuration)
      configuration="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "${output_bundle}" ]]; then
  echo "Usage: $0 --output <Renamr.app> [--repo-root <repo-root>] [--configuration release|debug]" >&2
  exit 1
fi

if [[ -z "${repo_root}" ]]; then
  script_dir="$(cd "$(dirname "$0")" && pwd)"
  repo_root="$(cd "${script_dir}/../.." && pwd)"
fi

macos_root="${repo_root}/macos"
if [[ ! -f "${macos_root}/Package.swift" ]]; then
  echo "Package.swift not found under ${macos_root}" >&2
  exit 1
fi

case "${configuration}" in
  release|debug) ;;
  *)
    echo "Unsupported configuration '${configuration}', expected release or debug." >&2
    exit 1
    ;;
esac

swift_flags=(-c "${configuration}")
if [[ "${configuration}" == "release" ]]; then
  swift_flags+=(--product Renamr --product RenamrPythonService)
fi

echo "Building Swift package (${configuration})..."
cd "${macos_root}"
swift build "${swift_flags[@]}"
bin_path="$(swift build --show-bin-path -c "${configuration}")"

app_binary="${bin_path}/Renamr"
service_binary="${bin_path}/RenamrPythonService"
sparkle_framework="${bin_path}/Sparkle.framework"

if [[ ! -x "${app_binary}" || ! -x "${service_binary}" ]]; then
  echo "Expected binaries not found under ${bin_path}" >&2
  exit 1
fi

if [[ ! -d "${sparkle_framework}" ]]; then
  echo "Sparkle.framework was not found under ${bin_path}" >&2
  exit 1
fi

app_bundle="${output_bundle}"
service_bundle="${app_bundle}/Contents/XPCServices/RenamrPythonService.xpc"

rm -rf "${app_bundle}"
mkdir -p \
  "${app_bundle}/Contents/MacOS" \
  "${app_bundle}/Contents/Frameworks" \
  "${app_bundle}/Contents/Resources" \
  "${service_bundle}/Contents/MacOS" \
  "${service_bundle}/Contents/Frameworks" \
  "${service_bundle}/Contents/Resources"

cp "${app_binary}" "${app_bundle}/Contents/MacOS/Renamr"
cp "${macos_root}/Renamr/Resources/Info.plist" "${app_bundle}/Contents/Info.plist"

cp "${service_binary}" "${service_bundle}/Contents/MacOS/RenamrPythonService"
cp "${macos_root}/RenamrPythonService/Info.plist" "${service_bundle}/Contents/Info.plist"

cp -R "${sparkle_framework}" "${app_bundle}/Contents/Frameworks/Sparkle.framework"

app_bundle_binary="${app_bundle}/Contents/MacOS/Renamr"
if ! otool -l "${app_bundle_binary}" | grep -q "@executable_path/../Frameworks"; then
  install_name_tool -add_rpath "@executable_path/../Frameworks" "${app_bundle_binary}"
fi

echo "Assembled app bundle at ${app_bundle}"
