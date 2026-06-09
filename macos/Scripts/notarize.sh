#!/usr/bin/env bash
set -euo pipefail

bundle=""
profile=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bundle)
      bundle="$2"
      shift 2
      ;;
    --keychain-profile)
      profile="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "${bundle}" || -z "${profile}" ]]; then
  echo "Usage: $0 --bundle <Renamr.app> --keychain-profile <notary-profile>" >&2
  exit 1
fi

tmp_zip="$(mktemp -t renamr-notary).zip"
trap 'rm -f "${tmp_zip}"' EXIT

ditto -c -k --keepParent "${bundle}" "${tmp_zip}"
xcrun notarytool submit "${tmp_zip}" --keychain-profile "${profile}" --wait
xcrun stapler staple "${bundle}"
xcrun stapler validate "${bundle}"
