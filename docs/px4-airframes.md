# Results for the airframe scripts shipped with PX4

The golden tests run the tool on every airframe script in
`ROMFS/px4fmu_common/init.d/airframes` and `init.d-posix/airframes` of a PX4
release. The reports are stored in `tests/golden/<PX4 version>/`, and
`index.json` there lists the status of every script.

## PX4 v1.17.0

| Status | Scripts |
|---|---|
| checked | 57 |
| unsupported `CA_AIRFRAME` | 57 |
| no parameters in the script | 16 |
| no `CA_*` parameters | 1 |

Unsupported scripts by `CA_AIRFRAME` value:

| `CA_AIRFRAME` | Scripts |
|---|---|
| 1 (fixed-wing) | 23 |
| 3 (tiltrotor VTOL) | 4 |
| 4 (tailsitter VTOL) | 6 |
| 5 (rover (Ackermann)) | 6 |
| 6 (rover (differential)) | 4 |
| 7 (motors (6DOF)) | 6 |
| 8 (multirotor with tilt) | 1 |
| 9 (custom) | 3 |
| 10 (helicopter (tail ESC)) | 1 |
| 13 (rover (mecanum)) | 1 |
| 14 (spacecraft 2D) | 2 |

### Findings

54 of the 57 checked scripts have no findings. Three have findings, all about
`CA_ROTOR_COUNT`:

| Script | Findings | Explanation |
|---|---|---|
| `init.d/airframes/4901_crazyflie21` | CA001, CA021 | The script sets `CA_ROTOR0_PX` to `CA_ROTOR3_KM` but not `CA_ROTOR_COUNT`, whose default is 0. No file it sources and no board default of that board sets it either. |
| `init.d-posix/airframes/3011_jsbsim_hexarotor_x` | CA001, CA021 | The same: six rotors are described, `CA_ROTOR_COUNT` is not set. |
| `init.d/airframes/1002_standard_vtol.hil` | CA021 | The script sets `CA_ROTOR_COUNT 5` and, further down, `CA_ROTOR_COUNT 4`. The last value wins, so rotor 4, the forward thrust motor, is not part of the allocation. |

The first two are reported as
[PX4 issue 29006](https://github.com/PX4/PX4-Autopilot/issues/29006). The
JSBSim hexarotor was started in PX4 v1.17.0 SITL, where
`control_allocator status` shows no configured actuators. Nothing was tried on
a Crazyflie, in the JSBSim simulation or in HIL, so whether these airframes
work in practice has not been checked.

The limit of rule CA010 was chosen with these scripts: the omnicopter airframes
have thrust gains of 1.66, below the default limit of 2.0.
