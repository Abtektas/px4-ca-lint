#!/usr/bin/env bash
# Build px4_ca_engine against a PX4 source tree without modifying that tree.
#
# usage: engine/build.sh <path to PX4-Autopilot> [build directory]
#
# PX4's build needs a Python with PX4's requirements installed. It is taken
# from PX4_CA_PYTHON if set, else from <PX4-Autopilot>/.venv, else from PATH.
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

# The engine does not need Gazebo. Skipping the lookup keeps the build
# independent of whatever Gazebo version is installed on the host.
PYTHON_ARGS=()
if [ -n "${PX4_CA_PYTHON:-}" ]; then
	PYTHON_ARGS=(-DPYTHON_EXECUTABLE="${PX4_CA_PYTHON}")
elif [ -x "${PX4_DIR}/.venv/bin/python" ]; then
	PYTHON_ARGS=(-DPYTHON_EXECUTABLE="${PX4_DIR}/.venv/bin/python")
fi

# On macOS, let the engine run on older systems than the one it is built on.
PLATFORM_ARGS=()
if [ "$(uname)" = "Darwin" ]; then
	PLATFORM_ARGS=(-DCMAKE_OSX_DEPLOYMENT_TARGET="${PX4_CA_MACOS_TARGET:-14.0}")
fi

cmake -S "${PX4_DIR}" -B "${BUILD_DIR}" -G Ninja \
	-DCONFIG=px4_sitl_default \
	-DCMAKE_BUILD_TYPE=RelWithDebInfo \
	-DEXTERNAL_MODULES_LOCATION="${HERE}" \
	-DCMAKE_DISABLE_FIND_PACKAGE_gz-transport=ON \
	-DCMAKE_DISABLE_FIND_PACKAGE_gz-sim=ON \
	-DCMAKE_DISABLE_FIND_PACKAGE_gz-sensors=ON \
	-DCMAKE_DISABLE_FIND_PACKAGE_gz-plugin=ON \
	-DCMAKE_DISABLE_FIND_PACKAGE_Protobuf=ON \
	${PLATFORM_ARGS[@]+"${PLATFORM_ARGS[@]}"} \
	${PYTHON_ARGS[@]+"${PYTHON_ARGS[@]}"}

cmake --build "${BUILD_DIR}" --target px4_ca_engine
echo "built: ${BUILD_DIR}/px4_ca_engine"
