#!/usr/bin/env bash
set -euo pipefail

updates_dir=""
sparkle_bin=""
key_file=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --updates-dir)
      updates_dir="$2"
      shift 2
      ;;
    --sparkle-bin)
      sparkle_bin="$2"
      shift 2
      ;;
    --key-file)
      key_file="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "${updates_dir}" ]]; then
  echo "Usage: $0 --updates-dir <dir> [--sparkle-bin <path>] [--key-file <pem>]" >&2
  exit 1
fi

if [[ -z "${sparkle_bin}" ]]; then
  sparkle_bin="/Applications/Sparkle/bin/generate_appcast"
fi

if [[ ! -x "${sparkle_bin}" ]]; then
  echo "Sparkle generate_appcast not found at ${sparkle_bin}" >&2
  exit 1
fi

cmd=("${sparkle_bin}" "${updates_dir}")
if [[ -n "${key_file}" ]]; then
  cmd+=("--ed-key-file" "${key_file}")
fi

"${cmd[@]}"
