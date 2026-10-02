# px4-ca-lint engine.
#
# Built as a PX4 "external modules" directory, so the PX4 tree is not modified:
#   cmake -S <PX4> -B <build> -G Ninja -DCONFIG=px4_sitl_test \
#         -DEXTERNAL_MODULES_LOCATION=<this repo>/engine
#   ninja -C <build> px4_ca_engine
#
# The px4_sitl_test config is used because it provides the `test_stubs` library,
# which lets a small host executable link the PX4 platform layer without the
# full module list.

# PX4 adds external modules before the platform layer, so `test_stubs` is not
# defined yet at this point. BUILD_TESTING is what makes PX4 define it later.
if(NOT BUILD_TESTING)
	message(FATAL_ERROR "px4_ca_engine needs the px4_sitl_test config (-DCONFIG=px4_sitl_test)")
endif()

execute_process(
	COMMAND git describe --tags --always --dirty
	WORKING_DIRECTORY ${PX4_SOURCE_DIR}
	OUTPUT_VARIABLE PX4_CA_ENGINE_PX4_VERSION
	OUTPUT_STRIP_TRAILING_WHITESPACE
)
execute_process(
	COMMAND git rev-parse HEAD
	WORKING_DIRECTORY ${PX4_SOURCE_DIR}
	OUTPUT_VARIABLE PX4_CA_ENGINE_PX4_COMMIT
	OUTPUT_STRIP_TRAILING_WHITESPACE
)

add_executable(px4_ca_engine EXCLUDE_FROM_ALL main.cpp)

target_compile_definitions(px4_ca_engine PRIVATE
	MODULE_NAME="px4_ca_engine"
	PX4_CA_ENGINE_PX4_VERSION="${PX4_CA_ENGINE_PX4_VERSION}"
	PX4_CA_ENGINE_PX4_COMMIT="${PX4_CA_ENGINE_PX4_COMMIT}"
)

# ControlAllocation::getDroppedAxes() was added after PX4 v1.17.0.
file(STRINGS ${PX4_SOURCE_DIR}/src/lib/control_allocation/control_allocation/ControlAllocation.hpp
	_dropped_axes_api REGEX "getDroppedAxes")

if(_dropped_axes_api)
	target_compile_definitions(px4_ca_engine PRIVATE PX4_CA_ENGINE_HAS_DROPPED_AXES)
endif()

set(_engine_libs
	VehicleActuatorEffectiveness
	ControlAllocation
	px4_layer
	px4_platform
	uORB
	systemlib
	cdev
	px4_work_queue
	px4_daemon
	work_queue
	parameters
	events
	perf
	tinybson
	uorb_msgs
)

# whole-archive so the daemon app-map stubs are linked
if(APPLE)
	list(APPEND _engine_libs test_stubs "-Wl,-force_load,$<TARGET_FILE:test_stubs>")
else()
	list(APPEND _engine_libs -Wl,--whole-archive test_stubs -Wl,--no-whole-archive)
endif()

target_link_libraries(px4_ca_engine PRIVATE ${_engine_libs})
