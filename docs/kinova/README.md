# Kinova Gen3

This guide describes the experimental Kinova Gen3 integration available in this repository.

[Project README](../../README.md) · [Camera guide](cameras.md) · [Upstream LeRobot documentation](https://huggingface.co/docs/lerobot/index)

## Project status

The integration supports Kinova Gen3 data collection, SO-101 leader-arm teleoperation, and policy rollout. It remains experimental and has limited hardware-validation coverage.

Current support status:

| Capability | Implementation status | Important caveat |
| --- | --- | --- |
| Kinova joint and gripper observations | Implemented | Limited hardware validation |
| Kinova joint and gripper commands | Implemented | Hard-coded controller gains and targets require site-specific review |
| SO-101 leader teleoperation | Implemented | Degree-based mapping with fixed offsets and signs |
| Kinova wrist camera | Implemented | RTSP latency may be unsuitable for closed-loop control |
| External OpenCV camera | Implemented | Recommended for latency-sensitive use |
| Dataset recording | Available through `lerobot-record` | Requires a teleoperator or policy |
| Policy rollout | Available through `lerobot-record` | Limited hardware validation |
| Standalone teleoperation CLI | Not registered | `lerobot-teleoperate` does not currently load the Kinova types |
| Replay, calibration, and motor setup CLIs | Not registered | Do not use their upstream examples for Kinova without additional integration |

## Demonstrations

<table>
  <tr>
    <td align="center"><img src="../../media/kinova_gen3/so101-leader-teleoperation.gif" alt="Teleoperating a Kinova Gen3 with an SO-101 leader arm" width="360"></td>
    <td align="center"><img src="../../media/kinova_gen3/vla-eraser-inference.gif" alt="Kinova Gen3 VLA inference moving an eraser into a box" width="360"></td>
  </tr>
  <tr>
    <td><strong>SO-101 leader-arm teleoperation.</strong> The apparent response lag shown here is due to conservative speed safety limits configured on the Kinova arm, not latency in the leader-arm interface.</td>
    <td><strong>VLA inference.</strong> The policy follows the prompt <em>“Pick up the eraser and put it in the box”</em> after fine-tuning on 40 episodes of the task. An additional webcam was mounted on the wrist and used instead of the integrated Kinova camera stream to avoid its latency.</td>
  </tr>
</table>

## Safety

> [!WARNING]
> This software can command a physical robot. Application software is not a safety system.

Before connecting:

- Clear people, tools, and obstructions from the workspace.
- Keep the physical emergency stop immediately accessible.
- Connect and verify a supported wired Xbox gamepad before starting. Keep it within reach until `lerobot-record` has exited and the robot is no longer receiving API commands; Kinova documents that physical gamepad input takes immediate precedence over API sessions. The gamepad is a supplemental override, not a replacement for the physical emergency stop. See the [Kinova Gen3 User Guide](https://www.kinovarobotics.com/uploads/User-Guide-Gen3-R07.pdf) for connection and control-mapping details.
- Confirm robot-level speed, force, workspace, and payload limits.
- Review the configured home position, joint directions, offsets, gains, and maximum speeds.
- Start without a payload and use conservative robot-level limits.
- Verify that the SO-101 mapping is appropriate for your robot mounting and task.
- Do not rely on the no-op teleoperator or `robot.no_op` as a hardware interlock.

Connecting the Kinova robot starts background measurement and tracking threads. The tracker has configured target positions and can issue joint-speed commands. Perform first connection and motion tests under the supervision of a person familiar with the Kinova safety system.

Collision avoidance, workspace protection zones, and environment-aware motion planning are not implemented by this integration.

## Requirements

You will need:

- A Kinova Gen3 reachable from the host computer.
- A supported Python environment for this LeRobot version.
- The Kinova Kortex API version supplied or otherwise installed for your system.
- An SO-101 leader arm for leader-arm teleoperation.
- A Feetech-compatible connection for the SO-101 leader.
- An optional external camera for lower-latency video.

## Installation

Clone this repository:

```bash
git clone https://github.com/JHUAPL/lerobot-kinova-gen3.git
cd lerobot-kinova-gen3
```

Create and activate an isolated Python environment, then install the Kinova and Feetech extras:

```bash
pip install -e ".[kinova,feetech]"
```

The `lerobot` package on PyPI does not contain the Kinova integration documented here.

The Kinova extra currently refers to a Kortex API wheel bundled under `kinova/`. This project treats the wheel as BSD-3-Clause licensed, consistent with Kinova's official Kortex repository. See [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md) for attribution and the reproduced license notice.

### Firmware compatibility

The bundled Python wheel is Kortex API `2.5.0.post6`. Kinova's official [Kortex API download table](https://github.com/Kinovarobotics/Kinova-kortex2_Gen3_G3L#download-links) provides paired firmware and API resources under **Release 2.5.0 for Gen3**. Confirm that the package is for the Gen3 rather than the Gen3 lite before installing it.

Firmware is installed through the Kortex Web App's **Systems > Upgrade** page. Follow the upgrade procedure and model-specific precautions in the [Kinova Gen3 User Guide](https://www.kinovarobotics.com/uploads/User-Guide-Gen3-R07.pdf). Consult Kinova support before upgrading or downgrading if the installed robot configuration does not match the documented release.

## Configuration values

Replace the placeholders in the examples with values for your installation:

| Placeholder | Meaning |
| --- | --- |
| `<KINOVA_IP>` | Kinova robot IP address |
| `<KINOVA_USERNAME>` | Kinova account username |
| `<KINOVA_PASSWORD>` | Kinova account password |
| `<ROBOT_ID>` | A stable, non-sensitive identifier for this robot configuration |
| `<SO101_SERIAL_PORT>` | Serial device for the SO-101 leader |
| `<LEADER_ID>` | A stable identifier for the leader arm |
| `<CAMERA_INDEX>` | OpenCV camera index discovered on the current host |
| `<HF_USER>/<DATASET_NAME>` | Dataset repository identifier |
| `<LOCAL_DATASET_DIRECTORY>` | Local dataset output directory |
| `<POLICY_PATH>` | Local or Hub policy checkpoint |

## Cameras

The integrated Kinova RTSP stream may have noticeable latency. For latency-sensitive work, use an externally mounted OpenCV camera. See the dedicated [Kinova camera guide](cameras.md) for configuration examples and limitations.

## SO-101 leader setup

Find the SO-101 leader's serial port using the upstream LeRobot port-discovery instructions. Use the port discovered on the current host; example ports from other systems are not portable.

The Kinova teleoperator type is `kinova_gen3_so101_leader`. It maps the SO-101 leader's available joints onto the seven Kinova joints and gripper using fixed offsets and direction signs. Two Kinova joints use fixed targets because the SO-101 leader has fewer corresponding arm degrees of freedom.

Before motion:

- Review the mapping in the source.
- Confirm the leader and robot start poses.
- Move the leader slowly through a small range.
- Verify every mapped joint direction independently.
- Stop immediately if any direction or offset is incorrect.

Only degree-based operation is currently implemented.

## Supported command-line entry points

### Record demonstrations with the SO-101 leader

The supported Kinova CLI path is `lerobot-record`. A documentation template is shown below; it is not directly executable until every placeholder is replaced:

```bash
lerobot-record \
  --robot.type=kinova_gen3 \
  --robot.ip=<KINOVA_IP> \
  --robot.kinova_user=<KINOVA_USERNAME> \
  --robot.kinova_pwd=<KINOVA_PASSWORD> \
  --robot.id=<ROBOT_ID> \
  --robot.cameras='<EXPLICIT_CAMERA_CONFIGURATION>' \
  --teleop.type=kinova_gen3_so101_leader \
  --teleop.port=<SO101_SERIAL_PORT> \
  --teleop.id=<LEADER_ID> \
  --dataset.repo_id=<HF_USER>/<DATASET_NAME> \
  --dataset.root=<LOCAL_DATASET_DIRECTORY> \
  --dataset.single_task="<TASK_DESCRIPTION>" \
  --dataset.num_episodes=<NUMBER_OF_EPISODES> \
  --dataset.push_to_hub=false \
  --display_data=true
```

Use a private dataset and remove sensitive imagery or metadata before any public upload.

### Run a policy and record evaluation episodes

Policy rollout also uses `lerobot-record`:

```bash
lerobot-record \
  --robot.type=kinova_gen3 \
  --robot.ip=<KINOVA_IP> \
  --robot.kinova_user=<KINOVA_USERNAME> \
  --robot.kinova_pwd=<KINOVA_PASSWORD> \
  --robot.id=<ROBOT_ID> \
  --robot.cameras='<EXPLICIT_CAMERA_CONFIGURATION>' \
  --policy.path=<POLICY_PATH> \
  --dataset.repo_id=<HF_USER>/<EVALUATION_DATASET_NAME> \
  --dataset.root=<LOCAL_DATASET_DIRECTORY> \
  --dataset.single_task="<TASK_DESCRIPTION>" \
  --dataset.num_episodes=<NUMBER_OF_EPISODES> \
  --dataset.push_to_hub=false
```

Policy output is passed to the real robot controller. Validate the policy, observation schema, action schema, camera ordering, units, and expected control rate before enabling motion.

### Fixed-action teleoperator

The `kinova_gen3_teleop_no_op` teleoperator emits fixed zero-valued joint and gripper actions. It exists to satisfy workflows that require a teleoperator object; it is not a simulator and does not mean that no hardware commands will occur.

Important distinctions:

- The robot still connects to physical hardware.
- Connecting starts background control threads.
- Zero-valued joint positions are valid position targets.
- `robot.no_op=true` suppresses joint-speed output in the tracker, but it does not constitute a complete hardware interlock and should not be assumed to suppress every actuator path.
- The physical emergency stop remains required.

This mode is not a safe dry run.

## Python entry points

The primary implementation classes are:

- `lerobot.robots.kinova_gen3.KinovaGen3`
- `lerobot.robots.kinova_gen3.KinovaGen3Config`
- `lerobot.cameras.kinova_gen3_vision.KinovaGen3VisionCamera`
- `lerobot.cameras.kinova_gen3_vision.KinovaGen3VisionCameraConfig`
- `lerobot.teleoperators.kinova_gen3_so101_leader.KinovaGen3So101Leader`
- `lerobot.teleoperators.kinova_gen3_so101_leader.KinovaGen3So101LeaderConfig`
- `lerobot.teleoperators.kinova_gen3_teleop_no_op.KinovaGen3TeleopNoOp`
- `lerobot.teleoperators.kinova_gen3_teleop_no_op.KinovaGen3TeleopNoOpConfig`

Prefer the documented `lerobot-record` workflow unless you understand LeRobot's robot, teleoperator, dataset, and cleanup lifecycles.

## Known limitations

- Hardware-validation coverage is limited.
- No automated Kinova hardware tests are included.
- Joint controller gains, speed limits, home positions, and SO-101 mappings are implementation defaults that require review.
- Collision avoidance and configurable workspace protection zones are not implemented.
- The Kinova wrist camera may have significant latency.
- Camera timing and control-loop timing are not guaranteed.
- The SO-101 mapping exposes fewer independently controlled arm degrees of freedom than the Kinova Gen3.
- Kinova support is registered in `lerobot-record`, but not in the standalone teleoperate, replay, calibration, or motor-setup commands.
- The fixed-action teleoperator and `robot.no_op` are not safety mechanisms.

## Troubleshooting

### Kinova type is not recognized

Confirm that you installed this source branch rather than the upstream PyPI package. Use `lerobot-record`; other upstream CLIs do not currently register the Kinova types.

### The external camera is not found

Run `lerobot-find-cameras opencv` on the machine that will perform recording. Replace the camera index after reconnecting devices or rebooting if enumeration changed.

### The wrist camera is delayed

Confirm that the robot network is not congested and that the host can decode the stream at the requested resolution and frame rate. If latency remains unacceptable, use an externally mounted OpenCV camera. Do not compensate for unknown delay by increasing robot speed.

### The leader direction or pose does not match the robot

Stop motion and review the fixed SO-101 offsets and signs before continuing. Do not attempt to correct a mapping error by moving faster or through a larger range.

## Reporting issues

When opening an issue, include:

- The commit hash.
- Operating system and Python version.
- Kinova model and firmware version.
- Kortex API version.
- Camera type and configuration.
- Whether the issue occurs before motion, during observation, or during command output.
- A sanitized command with credentials, IP addresses, usernames, hostnames, and private paths removed.
- Logs with private or identifying information removed.

State clearly whether the behavior was observed on hardware or inferred from static inspection.
