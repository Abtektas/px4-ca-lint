#!/usr/bin/env bash
# Build PX4 SITL (px4_sitl_default) for the cross-check in tests/test_sitl.py.
# The build directory is outside the PX4 tree.
#
# usage: engine/build_sitl.sh <path to PX4-Autopilot> [build directory]
#
# The Python for PX4's build is chosen as in engine/build.sh.
set -euo pipefail

if [ $# -lt 1 ]; then
	echo "usage: $0 <path to PX4-Autopilot> [build directory]" >&2
	exit 64
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PX4_DIR="$(cd "$1" && pwd -P)"
BUILD_DIR="${2:-${HERE}/../build/sitl}"
mkdir -p "${BUILD_DIR}"
BUILD_DIR="$(cd "${BUILD_DIR}" && pwd -P)"

PYTHON_ARGS=()
if [ -n "${PX4_CA_PYTHON:-}" ]; then
	PYTHON_ARGS=(-DPYTHON_EXECUTABLE="${PX4_CA_PYTHON}")
elif [ -x "${PX4_DIR}/.venv/bin/python" ]; then
	PYTHON_ARGS=(-DPYTHON_EXECUTABLE="${PX4_DIR}/.venv/bin/python")
fi

# The cross-check uses PX4's SIH simulation, which is part of PX4 itself.
# Gazebo and its Protobuf messages are skipped: they are not needed, and
# PX4 v1.17.0 does not build against every Gazebo and Protobuf version.
cmake -S "${PX4_DIR}" -B "${BUILD_DIR}" -G Ninja \
	-DCONFIG=px4_sitl_default \
	-DCMAKE_BUILD_TYPE=RelWithDebInfo \
	-DCMAKE_DISABLE_FIND_PACKAGE_gz-transport=ON \
	-DCMAKE_DISABLE_FIND_PACKAGE_gz-sim=ON \
	-DCMAKE_DISABLE_FIND_PACKAGE_gz-sensors=ON \
	-DCMAKE_DISABLE_FIND_PACKAGE_gz-plugin=ON \
	-DCMAKE_DISABLE_FIND_PACKAGE_Protobuf=ON \
	${PYTHON_ARGS[@]+"${PYTHON_ARGS[@]}"}

cmake --build "${BUILD_DIR}"
echo "built: ${BUILD_DIR}/bin/px4"
