#!/usr/bin/env bash
set -euo pipefail

bundle=""
repo_root=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bundle)
      bundle="$2"
      shift 2
      ;;
    --repo-root)
      repo_root="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "${bundle}" ]]; then
  echo "Usage: $0 --bundle <Renamr.app> [--repo-root <repo-root>]" >&2
  exit 1
fi

if [[ -z "${repo_root}" ]]; then
  script_dir="$(cd "$(dirname "$0")" && pwd)"
  repo_root="$(cd "${script_dir}/../.." && pwd)"
fi

service_bundle="${bundle}/Contents/XPCServices/RenamrPythonService.xpc"
service_frameworks="${service_bundle}/Contents/Frameworks"
runtime_root="${service_bundle}/Contents/Resources/python"

vendored_root="${repo_root}/macos/Vendored"
python_xcframework="${vendored_root}/Python.xcframework"
stdlib_src="${vendored_root}/python-stdlib"
packages_src="${vendored_root}/app_packages"
txt_process_src="${repo_root}/txt_process"

if [[ ! -d "${service_bundle}" ]]; then
  echo "Missing XPC service bundle at ${service_bundle}" >&2
  exit 1
fi

for required in "${python_xcframework}" "${stdlib_src}" "${packages_src}" "${txt_process_src}"; do
  if [[ ! -e "${required}" ]]; then
    echo "Missing required runtime input: ${required}" >&2
    echo "Run macos/Scripts/vendor_python.sh first." >&2
    exit 1
  fi
done

framework_src="${python_xcframework}/macos-arm64_x86_64/Python.framework"
if [[ ! -d "${framework_src}" ]]; then
  framework_src="$(find "${python_xcframework}" -type d -name "Python.framework" | head -n 1)"
fi
if [[ -z "${framework_src}" || ! -d "${framework_src}" ]]; then
  echo "Could not locate Python.framework inside ${python_xcframework}" >&2
  exit 1
fi

mkdir -p "${service_frameworks}"
rm -rf "${service_frameworks}/Python.framework"
cp -R "${framework_src}" "${service_frameworks}/Python.framework"

mkdir -p "${runtime_root}"
rm -rf \
  "${runtime_root}/python-stdlib" \
  "${runtime_root}/app_packages" \
  "${runtime_root}/txt_process" \
  "${runtime_root}/bin"

cp -R "${stdlib_src}" "${runtime_root}/python-stdlib"
cp -R "${packages_src}" "${runtime_root}/app_packages"
cp -R "${txt_process_src}" "${runtime_root}/txt_process"
mkdir -p "${runtime_root}/bin"

framework_python="${service_frameworks}/Python.framework/Versions/Current/bin/python3"
if [[ ! -x "${framework_python}" ]]; then
  echo "No executable Python launcher found at ${framework_python}." >&2
  echo "Implement embedded Python initialization or vendor a real launcher before packaging." >&2
  exit 1
fi

ln -sfn "../../../Frameworks/Python.framework/Versions/Current/bin/python3" "${runtime_root}/bin/python3"

echo "Prepared embedded Python runtime:"
echo "  framework: ${service_frameworks}/Python.framework"
echo "  runtime:   ${runtime_root}"
