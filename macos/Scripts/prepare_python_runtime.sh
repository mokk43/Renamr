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
  framework_src="$(find "${python_xcframework}" -type d -name "Python.framework" -print -quit)"
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

runtime_launcher="${runtime_root}/bin/python3"
framework_launcher="${service_frameworks}/Python.framework/Versions/Current/bin/python3"
framework_python_binary="${service_frameworks}/Python.framework/Versions/Current/Python"

is_shared_library() {
  local candidate="$1"
  file "${candidate}" 2>/dev/null | grep -qi "shared library"
}

build_launcher_from_framework() {
  local launcher_out="$1"
  local headers_dir="${service_frameworks}/Python.framework/Versions/Current/Headers"
  local source_file
  if [[ ! -d "${headers_dir}" ]]; then
    return 1
  fi
  if ! command -v clang >/dev/null 2>&1; then
    return 1
  fi
  source_file="$(mktemp "${TMPDIR:-/tmp}/renamr-python-launcher.XXXXXX.c")"
  cat > "${source_file}" <<'EOF'
#include <Python.h>
int main(int argc, char *argv[]) {
    return Py_BytesMain(argc, argv);
}
EOF
  if ! clang \
    "${source_file}" \
    -I"${headers_dir}" \
    -F"${service_frameworks}" \
    -framework Python \
    -Wl,-rpath,@executable_path/../../../Frameworks \
    -o "${launcher_out}"
  then
    rm -f "${source_file}"
    return 1
  fi
  rm -f "${source_file}"
  chmod +x "${launcher_out}"
}

rm -f "${runtime_launcher}"
if [[ -x "${framework_launcher}" ]]; then
  ln -sfn "../../../Frameworks/Python.framework/Versions/Current/bin/python3" "${runtime_launcher}"
elif [[ -x "${framework_python_binary}" ]]; then
  if is_shared_library "${framework_python_binary}"; then
    if ! build_launcher_from_framework "${runtime_launcher}"; then
      echo "Failed to build Python launcher from Python.framework." >&2
      exit 1
    fi
  else
    ln -sfn "../../../Frameworks/Python.framework/Versions/Current/Python" "${runtime_launcher}"
  fi
else
  echo "No executable Python launcher found in ${service_frameworks}/Python.framework." >&2
  exit 1
fi

echo "Prepared embedded Python runtime:"
echo "  framework: ${service_frameworks}/Python.framework"
echo "  runtime:   ${runtime_root}"
