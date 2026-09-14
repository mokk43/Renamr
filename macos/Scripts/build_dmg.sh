#!/usr/bin/env bash
set -euo pipefail

app_bundle=""
output_dmg=""
volume_name="Renamr"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app)
      app_bundle="$2"
      shift 2
      ;;
    --output)
      output_dmg="$2"
      shift 2
      ;;
    --volume-name)
      volume_name="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "${app_bundle}" || -z "${output_dmg}" ]]; then
  echo "Usage: $0 --app <Renamr.app> --output <Renamr.dmg>" >&2
  exit 1
fi

mkdir -p "$(dirname "${output_dmg}")"

if command -v create-dmg >/dev/null 2>&1; then
  create-dmg \
    --volname "${volume_name}" \
    --window-size 500 320 \
    --icon-size 100 \
    --icon "Renamr.app" 120 140 \
    --app-drop-link 380 140 \
    "${output_dmg}" \
    "${app_bundle}"
else
  echo "create-dmg not found, using hdiutil fallback layout."
  tmp_stage="$(mktemp -d)"
  trap 'rm -rf "${tmp_stage}"' EXIT
  cp -R "${app_bundle}" "${tmp_stage}/"
  hdiutil create \
    -volname "${volume_name}" \
    -srcfolder "${tmp_stage}" \
    -ov \
    -format UDZO \
    "${output_dmg}"
fi
