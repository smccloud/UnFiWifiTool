#!/usr/bin/env bash
#
# Generate OpenVEX exceptions for CVEs that are not applicable to this image.
#
# Usage:
#   ./scripts/generate-vex.sh [IMAGE] [OUTPUT_DIR]
#
# The image is inspected for the exact Debian package versions, so the VEX
# statements match what Docker Scout reports. The output directory defaults to
# .vex in the repository root.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${1:-${IMAGE:-unifi-wifi-tool:ci}}"
OUT_DIR="${2:-${ROOT}/.vex}"
VEX_AUTHOR="${VEX_AUTHOR:-security@smccloud.com}"

case "$OUT_DIR" in
  /*|[A-Za-z]:/*) ;;
  *) OUT_DIR="$ROOT/$OUT_DIR" ;;
esac
mkdir -p "$OUT_DIR"

generate_vex() {
  local cve="$1"
  local binary_package="$2"
  local source_package="$3"
  local justification="$4"
  local impact="$5"
  local output="$OUT_DIR/$cve.vex.json"

  docker run --rm -i --entrypoint python "$IMAGE" - \
    "$IMAGE" "$cve" "$binary_package" "$source_package" "$VEX_AUTHOR" "$justification" "$impact" \
    > "$output" <<'PY'
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

image_ref, cve, binary_package, source_package, author, justification, impact = sys.argv[1:8]


def read_os_release():
    values = {}
    for line in Path("/etc/os-release").read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value.strip().strip('"')
    return values


def package_version(name):
    return subprocess.check_output(
        ["dpkg-query", "-W", "-f=${Version}", name], text=True
    ).strip()


def image_purl(ref):
    ref = ref.removeprefix("docker.io/")
    if "@" in ref:
        repo, version = ref.rsplit("@", 1)
    else:
        slash = ref.rfind("/")
        colon = ref.rfind(":")
        if colon > slash:
            repo, version = ref[:colon], ref[colon + 1 :]
        else:
            repo, version = ref, "latest"
    return f"pkg:docker/{repo}@{version}"


os_release = read_os_release()
version = package_version(binary_package)
distro = os_release.get("VERSION_CODENAME") or os_release.get("DEBIAN_CODENAME", "")
os_name = os_release.get("ID", "debian")
os_version = os_release.get("VERSION_ID", "")
qualifiers = (
    f"os_distro={quote(distro, safe='')}"
    f"&os_name={quote(os_name, safe='')}"
    f"&os_version={quote(os_version, safe='')}"
)
subcomponent = (
    f"pkg:deb/{os_name}/{source_package}@{quote(version, safe='')}?{qualifiers}"
)

document = {
    "@context": "https://openvex.dev/ns/v0.2.0",
    "@id": f"https://smccloud.com/vex/{cve}",
    "author": author,
    "timestamp": datetime.now(timezone.utc)
    .replace(microsecond=0)
    .isoformat()
    .replace("+00:00", "Z"),
    "version": 1,
    "statements": [
        {
            "vulnerability": {"name": cve},
            "products": [
                {
                    "@id": image_purl(image_ref),
                    "subcomponents": [{"@id": subcomponent}],
                }
            ],
            "status": "not_affected",
            "justification": justification,
            "impact_statement": impact,
        }
    ],
}
print(json.dumps(document, indent=2))
PY

  printf 'wrote %s\n' "$output" >&2
}

generate_vex \
  "CVE-2005-2541" \
  "tar" \
  "tar" \
  "vulnerable_code_not_in_execute_path" \
  "The runtime image runs as the non-root app user and does not extract untrusted tar archives as root."

generate_vex \
  "CVE-2007-5686" \
  "passwd" \
  "shadow" \
  "vulnerable_code_not_present" \
  "The vulnerable rPath Linux initscripts are not present in this Debian-based image. The image does not run sshd or a login service and does not use /var/log/btmp."

generate_vex \
  "CVE-2010-0928" \
  "openssl" \
  "openssl" \
  "vulnerable_code_cannot_be_controlled_by_adversary" \
  "Exploitation requires physical control of the hardware to inject voltage faults. That threat model is not applicable to this container."
