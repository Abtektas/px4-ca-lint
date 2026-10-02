#!/usr/bin/env bash
# Build px4_ca_engine against a PX4 source tree without modifying that tree.
#
# usage: engine/build.sh <path to PX4-Autopilot> [build directory]
set -euo pipefail

if [ $# -lt 1 ]; then
	echo "usage: $0 <path to PX4-Autopilot> [build directory]" >&2
	exit 64
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PX4_DIR="$(cd "$1" && pwd -P)"
BUILD_DIR="${2:-${HERE}/../build/engine}"
mkdir -p "${BUILD_DIR}"
BUILD_DIR="$(cd "${BUILD_DIR}" && pwd -P)"

PYTHON_ARGS=()
if [ -x "${PX4_DIR}/.venv/bin/python" ]; then
	PYTHON_ARGS=(-DPYTHON_EXECUTABLE="${PX4_DIR}/.venv/bin/python")
fi

cmake -S "${PX4_DIR}" -B "${BUILD_DIR}" -G Ninja \
	-DCONFIG=px4_sitl_test \
	-DCMAKE_BUILD_TYPE=RelWithDebInfo \
	-DEXTERNAL_MODULES_LOCATION="${HERE}" \
	"${PYTHON_ARGS[@]}"

cmake --build "${BUILD_DIR}" --target px4_ca_engine
echo "built: ${BUILD_DIR}/px4_ca_engine"
