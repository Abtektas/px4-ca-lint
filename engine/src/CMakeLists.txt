# px4-ca-lint engine.
#
# Built as a PX4 "external modules" directory, so no file tracked by PX4 is
# modified:
#   cmake -S <PX4> -B <build> -G Ninja -DCONFIG=px4_sitl_default \
#         -DEXTERNAL_MODULES_LOCATION=<this repo>/engine
#   ninja -C <build> px4_ca_engine
#
# Only the px4_ca_engine target is built, not the PX4 firmware itself.

if(BUILD_TESTING)
	# PX4's test configuration enables sanitizers and defines the same app-map
	# functions as main.cpp.
	message(FATAL_ERROR "px4_ca_engine is built with -DCONFIG=px4_sitl_default, not with a test configuration")
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

target_link_libraries(px4_ca_engine PRIVATE ${_engine_libs})

# Fewer runtime dependencies for a binary that is copied to other machines.
if(NOT APPLE)
	target_link_options(px4_ca_engine PRIVATE -static-libstdc++ -static-libgcc)
endif()
