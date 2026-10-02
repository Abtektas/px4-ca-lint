#!/usr/bin/env bash
# Put a built engine into an archive with a checksum, and print what it needs
# from the system it runs on.
#
# usage: engine/package.sh <px4_ca_engine> <path to PX4-Autopilot> <platform, e.g. linux-x86_64> <output directory>
#
# The archive contains PX4's license text, because the engine contains compiled
# PX4 code.
set -euo pipefail

if [ $# -ne 4 ]; then
	echo "usage: $0 <px4_ca_engine> <path to PX4-Autopilot> <platform> <output directory>" >&2
	exit 64
fi

ENGINE="$1"
PX4_DIR="$2"
PLATFORM="$3"
OUT="$4"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

# the engine reports the PX4 version it was built against
printf 'CA_AIRFRAME 0\n' > "${WORK}/probe.params"
"${ENGINE}" "${WORK}/probe.params" "${WORK}/probe.json" > /dev/null 2>&1
PX4_VERSION="$(sed -n 's/.*"px4_version": "\(.*\)".*/\1/p' "${WORK}/probe.json")"
SCHEMA="$(sed -n 's/.*"engine_schema": \([0-9]*\).*/\1/p' "${WORK}/probe.json")"

if [ -z "${PX4_VERSION}" ] || [ -z "${SCHEMA}" ]; then
	echo "$0: could not read the PX4 version from the engine" >&2
	exit 1
fi

case "${PX4_VERSION}" in
*-dirty)
	echo "$0: the engine was built from a modified PX4 tree (${PX4_VERSION})" >&2
	exit 1
	;;
esac

NAME="px4_ca_engine-px4-${PX4_VERSION}-schema${SCHEMA}-${PLATFORM}"
mkdir -p "${OUT}" "${WORK}/${NAME}"
cp "${ENGINE}" "${WORK}/${NAME}/px4_ca_engine"
cp "${HERE}/../LICENSE" "${WORK}/${NAME}/LICENSE"
cp "${PX4_DIR}/LICENSE" "${WORK}/${NAME}/LICENSE-PX4"

{
	echo "px4_ca_engine for px4-ca-lint"
	echo "PX4 version: ${PX4_VERSION}"
	echo "engine_schema: ${SCHEMA}"
	echo "platform: ${PLATFORM}"
	echo
	echo "This program contains compiled code of the PX4 Autopilot project"
	echo "(https://github.com/PX4/PX4-Autopilot), copyright PX4 Development Team,"
	echo "licensed under the BSD 3-Clause license. Its license text is in LICENSE-PX4."
	echo "The px4-ca-lint code is licensed as stated in LICENSE."
	echo
	echo "Provided \"as is\", without warranty of any kind. See LICENSE."
} > "${WORK}/${NAME}/README.txt"

tar -C "${WORK}" -czf "${OUT}/${NAME}.tar.gz" "${NAME}"

(
	cd "${OUT}"

	if command -v sha256sum > /dev/null; then
		sha256sum "${NAME}.tar.gz" > "${NAME}.tar.gz.sha256"
	else
		shasum -a 256 "${NAME}.tar.gz" > "${NAME}.tar.gz.sha256"
	fi

	cat "${NAME}.tar.gz.sha256"
)

echo "--- runtime requirements"

if [ "$(uname)" = "Darwin" ]; then
	otool -L "${ENGINE}"
	otool -l "${ENGINE}" | grep -A4 LC_BUILD_VERSION | grep -E "minos|sdk"
else
	ldd "${ENGINE}" || true
	echo "highest glibc symbol version: $(objdump -T "${ENGINE}" | grep -o 'GLIBC_[0-9.]*' | sort -V | tail -1)"
fi
