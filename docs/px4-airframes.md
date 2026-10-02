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

55 of the 57 checked scripts have no findings. Two have one finding each:

| Script | Finding | Explanation |
|---|---|---|
| `init.d/airframes/4901_crazyflie21` | CA001 | The script sets `CA_ROTOR0_PX` to `CA_ROTOR3_KM` but not `CA_ROTOR_COUNT`, whose default is 0. No file it sources and no board default of that board sets it either. |
| `init.d-posix/airframes/3011_jsbsim_hexarotor_x` | CA001 | The same: six rotors are described, `CA_ROTOR_COUNT` is not set. |

Both were found by reading the scripts with this tool. They were not
reproduced on a vehicle or in the JSBSim simulation, so whether these airframes
work in practice has not been checked.

The limit of rule CA010 was chosen with these scripts: the omnicopter airframes
have thrust gains of 1.66, below the default limit of 2.0.
