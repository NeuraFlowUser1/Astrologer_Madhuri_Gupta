#!/usr/bin/env bash
set -euo pipefail
umask 077
if [[ $# != 1 || ! -d "$1" || -L "$1" || $(uname -s) != Linux || $(uname -m) != x86_64 ]]; then
  printf '%s\n' 'backup_tool_target_invalid' >&2
  exit 1
fi
BookingTools=$(realpath -- "$1")
BookingScratch=$(mktemp -d)
trap 'rm -rf -- "$BookingScratch"' EXIT
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 --max-time 180 \
  https://github.com/FiloSottile/age/releases/download/v1.3.2/age-v1.3.2-linux-amd64.tar.gz \
  --output "$BookingScratch/age.tar.gz"
(cd "$BookingScratch" && printf '%s\n' 'cbe24006683f8eb669266162894b9a522a1af52f2665fbc63a4bb032ed26ac10  age.tar.gz' | sha256sum --check --status)
tar --extract --gzip --file "$BookingScratch/age.tar.gz" --directory "$BookingScratch" age/age age/age-keygen
install -m 0700 "$BookingScratch/age/age" "$BookingTools/age"
install -m 0700 "$BookingScratch/age/age-keygen" "$BookingTools/age-keygen"
[[ $("$BookingTools/age" --version) == v1.3.2 ]]
