// SPDX-License-Identifier: BSD-3-Clause
//
// px4_ca_engine: load control allocation parameters from a file, run PX4's own
// actuator effectiveness and control allocation code, and write the resulting
// matrices as JSON.
//
// Usage: px4_ca_engine <params file> <output json>
//
// The params file has one "NAME VALUE" pair per line. Parameters that are not
// in the file keep the defaults compiled into PX4.

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include <platforms/posix/apps.h>
#include <px4_platform_common/param.h>
#include <uORB/Subscription.hpp>

#include <ControlAllocationPseudoInverse.hpp>
#include <ControlAllocationSequentialDesaturation.hpp>

#include "ActuatorEffectivenessMultirotor.hpp"
#include "ActuatorEffectivenessStandardVTOL.hpp"

// Version of the JSON document written by this program. Increase it whenever a
// field is removed or changes meaning.
static constexpr int ENGINE_SCHEMA_VERSION = 1;

static constexpr int EXIT_USAGE = 64;
static constexpr int EXIT_INPUT = 65;
static constexpr int EXIT_UNSUPPORTED = 66;
static constexpr int EXIT_PX4_FAILED = 67;

// PX4's daemon library expects the program to provide the list of built-in
// commands. The engine has none.
void init_app_map(apps_map_type &) {}
void list_builtins(apps_map_type &) {}

using Matrix6N = matrix::Matrix<float, ControlAllocation::NUM_AXES, ControlAllocation::NUM_ACTUATORS>;
using MatrixN6 = matrix::Matrix<float, ControlAllocation::NUM_ACTUATORS, ControlAllocation::NUM_AXES>;

// _mix is a protected member, so expose it through a subclass.
template <class Base>
class Inspectable : public Base
{
public:
	const MatrixN6 &mix()
	{
		this->updatePseudoInverse();
		return this->_mix;
	}
};

static const char *const AXIS_NAMES[ControlAllocation::NUM_AXES] = {
	"roll", "pitch", "yaw", "thrust_x", "thrust_y", "thrust_z"
};

static void writeNumber(FILE *out, float value)
{
	if (std::isfinite(value)) {
		fprintf(out, "%.9g", (double)value);

	} else {
		fputs("null", out);
	}
}

static int loadParams(const char *path, FILE *out)
{
	FILE *file = fopen(path, "r");

	if (!file) {
		fprintf(stderr, "px4_ca_engine: cannot open %s\n", path);
		return -1;
	}

	char line[256];
	int num_set = 0;
	bool first_unknown = true;

	fputs("  \"unknown_parameters\": [", out);

	while (fgets(line, sizeof(line), file)) {
		char name[64];
		double value;

		if (line[0] == '#' || sscanf(line, " %63s %lf", name, &value) != 2) {
			continue;
		}

		param_t handle = param_find(name);

		if (handle == PARAM_INVALID) {
			fprintf(out, "%s\"%s\"", first_unknown ? "" : ", ", name);
			first_unknown = false;
			continue;
		}

		if (param_type(handle) == PARAM_TYPE_INT32) {
			int32_t int_value = (int32_t)std::lround(value);
			param_set_no_notification(handle, &int_value);

		} else {
			float float_value = (float)value;
			param_set_no_notification(handle, &float_value);
		}

		num_set++;
	}

	fputs("],\n", out);
	fclose(file);
	return num_set;
}

static const char *methodName(AllocationMethod method)
{
	switch (method) {
	case AllocationMethod::PSEUDO_INVERSE: return "pseudo_inverse";

	case AllocationMethod::SEQUENTIAL_DESATURATION: return "sequential_desaturation";

	default: return "unknown";
	}
}

int main(int argc, char **argv)
{
	if (argc != 3) {
		fprintf(stderr, "usage: px4_ca_engine <params file> <output json>\n");
		return EXIT_USAGE;
	}

	uORB::Manager::initialize();
	param_init();
	param_control_autosave(false);

	FILE *out = fopen(argv[2], "w");

	if (!out) {
		fprintf(stderr, "px4_ca_engine: cannot write %s\n", argv[2]);
		return EXIT_INPUT;
	}

	fputs("{\n", out);
	fprintf(out, "  \"engine_schema\": %d,\n", ENGINE_SCHEMA_VERSION);
	fprintf(out, "  \"px4_version\": \"%s\",\n", PX4_CA_ENGINE_PX4_VERSION);
	fprintf(out, "  \"px4_commit\": \"%s\",\n", PX4_CA_ENGINE_PX4_COMMIT);

	const int num_set = loadParams(argv[1], out);

	if (num_set < 0) {
		fclose(out);
		return EXIT_INPUT;
	}

	fprintf(out, "  \"parameters_set\": %d,\n", num_set);

	int32_t airframe = 0;
	param_get(param_find("CA_AIRFRAME"), &airframe);
	fprintf(out, "  \"ca_airframe\": %d,\n", (int)airframe);

	// Same selection as ControlAllocator::update_effectiveness_source().
	ActuatorEffectiveness *effectiveness = nullptr;

	switch (airframe) {
	case 0: effectiveness = new ActuatorEffectivenessMultirotor(nullptr); break;

	case 2: effectiveness = new ActuatorEffectivenessStandardVTOL(nullptr); break;

	default:
		fprintf(out, "  \"error\": \"unsupported CA_AIRFRAME\"\n}\n");
		fclose(out);
		return EXIT_UNSUPPORTED;
	}

	fprintf(out, "  \"effectiveness_source\": \"%s\",\n", effectiveness->name());

	ActuatorEffectiveness::Configuration config{};

	if (!effectiveness->getEffectivenessMatrix(config, EffectivenessUpdateReason::CONFIGURATION_UPDATE)) {
		fprintf(out, "  \"error\": \"PX4 did not produce an effectiveness matrix\"\n}\n");
		fclose(out);
		return EXIT_PX4_FAILED;
	}

	fprintf(out, "  \"num_motors\": %d,\n", config.num_actuators[(int)ActuatorType::MOTORS]);
	fprintf(out, "  \"num_servos\": %d,\n", config.num_actuators[(int)ActuatorType::SERVOS]);

	AllocationMethod methods[ActuatorEffectiveness::MAX_NUM_MATRICES] {};
	effectiveness->getDesiredAllocationMethod(methods);
	bool normalize_rpy[ActuatorEffectiveness::MAX_NUM_MATRICES] {};
	effectiveness->getNormalizeRPY(normalize_rpy);

	fputs("  \"matrices\": [\n", out);

	for (int i = 0; i < effectiveness->numMatrices(); i++) {
		const int num_actuators = config.num_actuators_matrix[i];
		Matrix6N &matrix = config.effectiveness_matrices[i];

		// ControlAllocator::update_effectiveness_matrix_if_needed() zeroes the rows
		// of axes with only marginal authority before the matrix is inverted.
		bool weak_axis[ControlAllocation::NUM_AXES] {};

		for (int axis = 0; axis < ControlAllocation::NUM_AXES; axis++) {
			bool all_entries_small = true;
			bool any_entry_nonzero = false;

			for (int m = 0; m < num_actuators; m++) {
				if (fabsf(matrix(axis, m)) > 0.05f) {
					all_entries_small = false;
				}

				if (fabsf(matrix(axis, m)) > 0.f) {
					any_entry_nonzero = true;
				}
			}

			if (all_entries_small) {
				matrix.row(axis) = 0.f;
				weak_axis[axis] = any_entry_nonzero;
			}
		}

		Inspectable<ControlAllocationPseudoInverse> pseudo_inverse;
		Inspectable<ControlAllocationSequentialDesaturation> sequential_desaturation;
		const bool sequential = (methods[i] == AllocationMethod::SEQUENTIAL_DESATURATION);
		ControlAllocation &allocation = sequential ? static_cast<ControlAllocation &>(sequential_desaturation)
						: static_cast<ControlAllocation &>(pseudo_inverse);

		allocation.setNormalizeRPY(normalize_rpy[i]);
		allocation.setEffectivenessMatrix(matrix, config.trim[i], config.linearization_point[i], num_actuators, true);
		const MatrixN6 &mix = sequential ? sequential_desaturation.mix() : pseudo_inverse.mix();

		fprintf(out, "    {\n      \"index\": %d,\n      \"num_actuators\": %d,\n", i, num_actuators);
		fprintf(out, "      \"method\": \"%s\",\n", methodName(methods[i]));
		fprintf(out, "      \"normalize_rpy\": %s,\n", normalize_rpy[i] ? "true" : "false");
#if defined(PX4_CA_ENGINE_HAS_DROPPED_AXES)
		fprintf(out, "      \"dropped_axes_bitmask\": %d,\n", (int)allocation.getDroppedAxes());
#else
		// this PX4 version does not report dropped axes
		fputs("      \"dropped_axes_bitmask\": null,\n", out);
#endif

		// Actuators are numbered across all matrices, motors first, then servos.
		fputs("      \"actuators\": [", out);
		bool first = true;
		const int num_motors = config.num_actuators[(int)ActuatorType::MOTORS];

		for (int k = 0; k < config.totalNumActuators(); k++) {
			if (config.matrix_selection_indexes[k] != i) {
				continue;
			}

			if (k < num_motors) {
				fprintf(out, "%s{\"type\": \"motor\", \"index\": %d}", first ? "" : ", ", k);

			} else {
				fprintf(out, "%s{\"type\": \"servo\", \"index\": %d}", first ? "" : ", ", k - num_motors);
			}

			first = false;
		}

		fputs("],\n", out);

		fputs("      \"weak_axes_zeroed\": [", out);
		first = true;

		for (int axis = 0; axis < ControlAllocation::NUM_AXES; axis++) {
			if (weak_axis[axis]) {
				fprintf(out, "%s\"%s\"", first ? "" : ", ", AXIS_NAMES[axis]);
				first = false;
			}
		}

		fputs("],\n", out);

		fputs("      \"effectiveness\": {\n", out);

		for (int axis = 0; axis < ControlAllocation::NUM_AXES; axis++) {
			fprintf(out, "        \"%s\": [", AXIS_NAMES[axis]);

			for (int m = 0; m < num_actuators; m++) {
				if (m > 0) { fputs(", ", out); }

				writeNumber(out, allocation.getEffectivenessMatrix()(axis, m));
			}

			fprintf(out, "]%s\n", axis + 1 < ControlAllocation::NUM_AXES ? "," : "");
		}

		fputs("      },\n      \"mix\": [\n", out);

		for (int m = 0; m < num_actuators; m++) {
			fputs("        {", out);

			for (int axis = 0; axis < ControlAllocation::NUM_AXES; axis++) {
				fprintf(out, "%s\"%s\": ", axis > 0 ? ", " : "", AXIS_NAMES[axis]);
				writeNumber(out, mix(m, axis));
			}

			fprintf(out, "}%s\n", m + 1 < num_actuators ? "," : "");
		}

		fprintf(out, "      ]\n    }%s\n", i + 1 < effectiveness->numMatrices() ? "," : "");
	}

	fputs("  ]\n}\n", out);
	fclose(out);
	delete effectiveness;
	return 0;
}
