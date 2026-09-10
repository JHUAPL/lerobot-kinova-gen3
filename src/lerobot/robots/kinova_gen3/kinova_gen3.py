import contextlib
import logging
import math
import os
import threading
import time
from functools import cached_property
from typing import Any

from kortex_api.autogen.client_stubs.BaseClientRpc import BaseClient
from kortex_api.autogen.client_stubs.ControlConfigClientRpc import ControlConfigClient
from kortex_api.autogen.client_stubs.DeviceConfigClientRpc import DeviceConfigClient
from kortex_api.autogen.client_stubs.DeviceManagerClientRpc import DeviceManagerClient
from kortex_api.autogen.client_stubs.VisionConfigClientRpc import VisionConfigClient
from kortex_api.autogen.messages import (
    Base_pb2,
    ControlConfig_pb2,
    DeviceConfig_pb2,
    Session_pb2,
)
from kortex_api.RouterClient import RouterClient, RouterClientSendOptions
from kortex_api.SessionManager import SessionManager
from kortex_api.TCPTransport import TCPTransport

from lerobot.cameras.utils import make_cameras_from_configs
from lerobot.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError

from ..robot import Robot
from .config_kinova_gen3 import KinovaGen3Config

# TODO Make a protection zone which is referenced prior to sending a position command. One for table, one for behind the robot. Could either use KortexAPI / MoveIt or just code up simple forward dyn.

# Create closure to set an event after an END or an ABORT
def check_for_end_or_abort(e):
    """Return a closure checking for END or ABORT notifications

    Arguments:
    e -- event to signal when the action is completed
        (will be set when an END or ABORT occurs)
    """

    def check(notification, e=e):
        print("EVENT : " + Base_pb2.ActionEvent.Name(notification.action_event))
        if (
            notification.action_event == Base_pb2.ACTION_END
            or notification.action_event == Base_pb2.ACTION_ABORT
        ):
            e.set()

    return check


logger = logging.getLogger(__name__)


class KinovaGen3(Robot):
    config_class = KinovaGen3Config
    name = "kinova_gen3"

    def __init__(self, config: KinovaGen3Config):
        super().__init__(config)
        self.config = config

        self.transport = TCPTransport()
        self.router = RouterClient(self.transport, RouterClient.basicErrorCallback)

        self.base: BaseClient | None = None
        self.control_config: ControlConfigClient | None = None
        self.session_manager: SessionManager | None = None
        self.device_config: DeviceConfigClient | None = None
        self.device_manager: DeviceManagerClient | None = None
        self.vision_config: VisionConfigClient | None = None

        self.cameras = make_cameras_from_configs(config.cameras)

        # --- measured state (sensor reading thread) ---
        self._measure_thread: threading.Thread | None = None
        self._measure_stop = threading.Event()
        self._state_lock = threading.Lock()
        self._latest_joint_positions_deg: list[float] = [0.0] * 7  # 7 joint positions (degrees)
        self._latest_gripper_position: float = 0.0

        # === tracker state ===
        self._tracker_thread: threading.Thread | None = None
        self._tracker_stop = threading.Event()
        self._tracker_lock = threading.Lock()
        self._tracker_home_position_deg = [0.0, 15.0, 180.0, 230.0, 0.0, 55.0, 90.0]
        self._latest_target_deg = list(self._tracker_home_position_deg)  # 7 joint desired positions (deg)

        # tunables (can move to config)
        self._rate_hz = getattr(self.config, "tracker_rate_hz", 50.0)
        self._kp = getattr(self.config, "kp_deg_per_deg", 1.5)
        self._max_speed = getattr(self.config, "max_speed_deg_s", 20.0)
        self._deadband = getattr(self.config, "deadband_deg", 0.5)

        # --- gripper target (teleop publishes this) ---
        self._latest_gripper_target_pos = 0.0   # normalized [0,1]
        self._gripper_home_position = 0.0

        # --- gripper control knobs (tune or move to config) ---
        self._gripper_rate_hz = getattr(self.config, "gripper_rate_hz", 20.0)
        self._gripper_kp = getattr(self.config, "gripper_kp_per_unit", 0.15)    # speed per unit pos error
        self._gripper_deadband = getattr(self.config, "gripper_deadband", 0.01) # error threshold in position units
        self._gripper_max_speed = getattr(self.config, "gripper_max_speed", 0.75) # clamp in [-1,1]

        # --- tracker-local bookkeeping (only touched by tracker thread) ---
        self._last_gripper_speed_sent = 0.0
        self._last_gripper_ts = 0.0

    # Properties
    @property
    def _motors_ft(self) -> dict[str, type]:
        # TODO Hard coded, is there a better way to do this without running connect first?
        # Joint positions
        obs_dict = {
            "joint_id_0.pos": float,
            "joint_id_1.pos": float,
            "joint_id_2.pos": float,
            "joint_id_3.pos": float,
            "joint_id_4.pos": float,
            "joint_id_5.pos": float,
            "joint_id_6.pos": float,
            "gripper.pos": float,
        }

        # gripper position
        obs_dict["gripper.pos"] = float
        return obs_dict

    @property
    def _cameras_ft(self) -> dict[str, tuple]:
        return {
            cam: (self.config.cameras[cam].height, self.config.cameras[cam].width, 3)
            for cam in self.cameras
        }

    @cached_property
    def observation_features(self) -> dict:
        """
        A dictionary describing the structure and types of the observations produced by the robot.
        Its structure (keys) should match the structure of what is returned by :pymeth:`get_observation`.
        Values for the dict should either be:
            - The type of the value if it's a simple value, e.g. `float` for single proprioceptive value (a joint's position/velocity)
            - A tuple representing the shape if it's an array-type value, e.g. `(height, width, channel)` for images

        Note: this property should be able to be called regardless of whether the robot is connected or not.
        """
        return {**self._motors_ft, **self._cameras_ft}

    @cached_property
    def action_features(self) -> dict:
        """
        A dictionary describing the structure and types of the actions expected by the robot. Its structure
        (keys) should match the structure of what is passed to :pymeth:`send_action`. Values for the dict
        should be the type of the value if it's a simple value, e.g. `float` for single proprioceptive value
        (a joint's goal position/velocity)

        Note: this property should be able to be called regardless of whether the robot is connected or not.
        """
        # TODO: THIS WILL BE UDDATED
        action_dict = {
            "joint_id_0.pos": float,
            "joint_id_1.pos": float,
            "joint_id_2.pos": float,
            "joint_id_3.pos": float,
            "joint_id_4.pos": float,
            "joint_id_5.pos": float,
            "joint_id_6.pos": float,
            "gripper.pos": float,
        }
        return action_dict

    @property
    def is_connected(self) -> bool:
        """
        Whether the robot is currently connected or not. If `False`, calling :pymeth:`get_observation` or
        :pymeth:`send_action` should raise an error.
        """
        # TODO: Make this better, not sure this is verifying we can talk to self.base
        # self.base.isAlive()
        return self.transport.tcp_transport_thread.is_alive() and all(
            cam.is_connected for cam in self.cameras.values()
        )

    @property
    def is_calibrated(self) -> bool:
        """Whether the robot is currently calibrated or not. Should be always `True` if not applicable"""
        return True

    # Startup / Stop Methods
    def connect(self):

        if self.is_connected:
            raise DeviceAlreadyConnectedError(f"{self} already connected")

        self.transport.connect(self.config.ip, self.config.port)

        if self.config.kinova_user != "":
            session_info = Session_pb2.CreateSessionInfo()
            session_info.username = self.config.kinova_user
            session_info.password = self.config.kinova_pwd
            session_info.session_inactivity_timeout = (
                self.config.session_inactivity_timeout
            )  # (milliseconds)
            session_info.connection_inactivity_timeout = (
                self.config.connection_inactivity_timeout
            )  # (milliseconds)

            self.session_manager = SessionManager(self.router)
            print("Logging as", self.config.kinova_user, "on device", self.config.ip)
            self.session_manager.CreateSession(session_info)

        self.base = BaseClient(self.router)
        self.control_config = ControlConfigClient(self.router)
        self.device_config = DeviceConfigClient(self.router)
        self.device_manager = DeviceManagerClient(self.router)
        self.vision_config = VisionConfigClient(self.router)

        for cam in self.cameras.values():
            if cam.config.type == "kinova_gen3_vision":
                cam.connect(self.vision_config, self.device_manager)
            else:
                cam.connect()

        self.configure()

        # Perform initial state measurement to populate cache (NEW)
        initial_joint_angles = self.base.GetMeasuredJointAngles()  # blocking call once
        js = sorted(initial_joint_angles.joint_angles, key=lambda j: j.joint_identifier)
        joint_vals = [float(j.value) for j in js]
        gripper_request = Base_pb2.GripperRequest()
        gripper_request.mode = Base_pb2.GRIPPER_POSITION
        initial_gripper = self.base.GetMeasuredGripperMovement(gripper_request)
        gripper_val = float(initial_gripper.finger[0].value)
        with self._state_lock:
            self._latest_joint_positions_deg = joint_vals
            self._latest_gripper_position = gripper_val

        # Start background thread to continuously update state (NEW)
        self.start_measure_thread()

        self.start_tracker()  # <— start streaming
        logger.info(f"{self} connected.")

    def configure(self) -> None:
        """
        Apply any one-time or runtime configuration to the robot.
        This may include setting motor parameters, control modes, or initial state.

        For now, relying on user to set and maintain consisten configs, i.e. via web gui, other than camera FPS and resolution
        """
        # TODO:  send to initial position (there should be examples which address this)

        # Make sure the arm is in Single Level Servoing mode
        base_servo_mode = Base_pb2.ServoingModeInformation()
        base_servo_mode.servoing_mode = Base_pb2.SINGLE_LEVEL_SERVOING
        self.base.SetServoingMode(base_servo_mode)

        # Get device id, not sure  if needed, default might be ok
        # device_id = self._get_device_id()

        # TODO: Set to default soft limits. Can't set globally, need to specify something other than UNSPECIFIED CONTROL MODE
        # control_mode = ControlConfig_pb2.UNSPECIFIED_CONTROL_MODE
        # control_mode_information = ControlConfig_pb2.ControlModeInformation(
        #    control_mode=control_mode
        # )

        # self.control_config.ResetJointSpeedSoftLimits(
        #    control_mode_information, device_id
        # )
        # self.control_config.ResetJointAccelerationSoftLimits(
        #    control_mode_information, device_id
        # )
        # TODO: Update with custom speed settings if needed. Note these calls aren't fully defined
        # self.control_config.SetJointSpeedSoftLimits
        # self.control_config.SetJointAccelerationSoftLimits

        # TODO add Twist Limits
        # self.control_config.SetTwistAngularSoftLimit
        # self.control_config.SetTwistLinearSoftLimit

    def disconnect(self) -> None:
        """Disconnect from the robot and perform any necessary cleanup."""
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")

        self.stop_tracker()
        self.stop_measure_thread()

        for cam in self.cameras.values():
            cam.disconnect()

        if self.session_manager is not None:

            router_options = RouterClientSendOptions()
            router_options.timeout_ms = 1000

            self.session_manager.CloseSession(router_options)

        self.transport.disconnect()

        logger.info(f"{self} disconnected.")

    # Core Methods
    def get_observation(self) -> dict[str, Any]:
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")

        # Read arm state from cached values (non-blocking)
        start = time.perf_counter()
        with self._state_lock:
            joint_vals = list(self._latest_joint_positions_deg)
            gripper_val = float(self._latest_gripper_position)
        obs_dict = {f"joint_id_{i}.pos": joint_vals[i] for i in range(len(joint_vals))}
        obs_dict["gripper.pos"] = gripper_val

        dt_ms = (time.perf_counter() - start) * 1e3
        logger.debug(
            f"{self} read state: {dt_ms:.1f}ms"
        )

        # Capture images from cameras
        for cam_key, cam in self.cameras.items():
            start = time.perf_counter()
            obs_dict[cam_key] = cam.async_read(500)
            dt_ms = (time.perf_counter() - start) * 1e3
            logger.debug(f"{self} read {cam_key}: {dt_ms:.1f}ms")

        return obs_dict

    def send_action(self, action: dict[str, Any]) -> dict[str, Any]:
        """
        Update the background tracker’s desired joint *positions* (deg).

        Track a desired joint *position* by sending proportional joint *velocity* (deg/s).

        Also tracks desired gripper position.

        Args:
            action (dict[str, Any]): Dictionary representing the desired action. Its structure should match
                :pymeth:`action_features`.

        # Example action dict
        #action = {
        #    "joint_id_0.pos": float,
        #    "joint_id_1.pos": float,
        #    "joint_id_2.pos": float,
        #    "joint_id_3.pos": float,
        #    "joint_id_4.pos": float,
        #    "joint_id_5.pos": float,
        #    "joint_id_6.pos": float,
        #    "gripper.pos": float,
        #

        Returns:
            dict[str, Any]: The action actually sent to the motors potentially clipped or modified, e.g. by
                safety limits on velocity.
        """

        # if not self.is_connected:
        #    raise DeviceNotConnectedError(f"{self} is not connected.")

        target = []
        for j in range(7):
            key = f"joint_id_{j}.pos"
            val = action.get(key)
            if val is None:
                with self._tracker_lock:
                    val = self._latest_target_deg[j]
            target.append(float(val))

        with self._tracker_lock:
            self._latest_target_deg = target

        # gripper (normalized 0..1)
        g = action.get("gripper.pos")
        if g is not None:
            with self._tracker_lock:
                #self._latest_gripper_target_pos = 1 - g # flipped convention
                self._latest_gripper_target_pos = g

        ## TODO: Could actually consider returning joint speeds as action here, since this will likely be how we control across teleop types
        # However, would need to make sure that send action knows hor to process positions vs actions...
        return action

    def calibrate(self) -> None:
        """
        Calibrate the robot if applicable. If not, this should be a no-op.

        This method should collect any necessary data (e.g., motor offsets) and update the
        :pyattr:`calibration` dictionary accordingly.
        """
        pass

    def _measure_loop(self):
        """Background thread loop to continuously read joint angles and gripper position."""
        period = 1.0 / max(
            1e-6, float(self._rate_hz)
        )  # aim for roughly self._rate_hz frequency
        next_t = time.perf_counter()
        gripper_request = Base_pb2.GripperRequest()
        gripper_request.mode = Base_pb2.GRIPPER_POSITION

        while not self._measure_stop.is_set():
            try:
                # Get latest joint angles
                joint_angles = self.base.GetMeasuredJointAngles()
                js = sorted(joint_angles.joint_angles, key=lambda j: j.joint_identifier)
                joint_vals = [float(j.value) for j in js]
                # Get latest gripper position
                measured_gripper = self.base.GetMeasuredGripperMovement(gripper_request)
                pos = float(measured_gripper.finger[0].value)
                # Update cached values (thread-safe)
                with self._state_lock:
                    self._latest_joint_positions_deg = joint_vals
                    self._latest_gripper_position = pos
            except Exception as e:
                logger.exception("Measure loop error: %s", e)
                break  # exit loop on error (e.g., connection loss)

            # Rate control to approx self._rate_hz (e.g. ~50 Hz)
            next_t += period
            sleep_s = next_t - time.perf_counter()
            if sleep_s > 0:
                time.sleep(sleep_s)
            else:
                next_t = time.perf_counter()  # adjust if we're running behind

    def start_measure_thread(self):
        """Start the background state measurement thread."""
        if self._measure_thread and self._measure_thread.is_alive():
            return  # already running
        self._measure_stop.clear()
        self._measure_thread = threading.Thread(
            target=self._measure_loop, name=f"{self.name}-measure", daemon=True
        )
        self._measure_thread.start()
        logger.info(
            f"Started measurement thread at ~{self._rate_hz:.1f} Hz"
        )  # log thread start

    def stop_measure_thread(self):
        """Stop the measurement thread."""
        if not self._measure_thread:
            return
        self._measure_stop.set()
        self._measure_thread.join(timeout=2.0)
        self._measure_thread = None
        logger.info("Stopped measurement thread")

    # Position Tracker Thread
    def _tracker_loop(self):
        period = 1.0 / max(1e-6, float(self._rate_hz))
        next_t = time.perf_counter()

        while not self._tracker_stop.is_set():
            try:
                # if not self.is_connected or self.base is None:
                #    time.sleep(0.1)
                #    next_t = time.perf_counter()
                #    continue

                # snapshot latest target
                with self._tracker_lock:
                    target = list(self._latest_target_deg)

                # read current joints
                q = self._read_joint_positions_deg()

                assert len(q) == len(
                    target
                ), "Kinova joint position list and SO101 leader joint pos list should be same length"
                n = len(q)
                speeds: list[float] = []
                for j in range(n):
                    err = self._angle_diff_deg(target[j], q[j])  # always shortest-angle
                    if abs(err) <= self._deadband:
                        v = 0.0
                    else:
                        v = self._kp * err
                        # clamp
                        v = (
                            min(v, self._max_speed)
                            if v > 0
                            else max(v, -self._max_speed)
                        )
                    speeds.append(v)

                # stream
                if self.config.no_op:
                    speeds = [0] * n

                self._send_joint_speeds_deg_s(speeds)

            except Exception as e:
                logger.exception("Tracker loop error; stopping streaming: %s", e)
                with contextlib.suppress(Exception):
                    self._send_joint_speeds_deg_s([0.0] * 7)
                time.sleep(0.25)

            # --- Gripper position → speed control @ gripper_rate_hz ---
            try:
                with self._tracker_lock:
                    g_target = float(self._latest_gripper_target_pos)

                g_meas = self._read_gripper_position()

                #print(f"meas {g_meas}, targ {g_target}")

                err = g_target - g_meas
                if abs(err) <= self._gripper_deadband:
                    g_speed = 0.0
                else:
                    g_speed = self._gripper_kp * err
                    g_speed = max(
                        -self._gripper_max_speed, min(self._gripper_max_speed, g_speed)
                    )

                # rate gating
                now = time.perf_counter()
                grip_period = 1.0 / max(1e-6, float(self._gripper_rate_hz))
                changed = abs(g_speed - self._last_gripper_speed_sent) > 1e-3
                timed_out = (now - self._last_gripper_ts) >= grip_period

                # print(f"Changed {changed}, Speed {abs(g_speed)}, Timed Out {timed_out}")

                # Send immediately on change; otherwise keep-alive at gripper_rate_hz while moving
                if changed or (abs(g_speed) > 1e-6 and timed_out):
                    self._send_gripper_speed(-g_speed) # sign flip due to backwards kinova convention

            except Exception as e:
                logger.exception("Gripper control step failed")
                print("Gripper error occured: ",e)

            # rate keeping
            acheived_rate_hz = 1 / (time.perf_counter() - next_t)
            next_t += period
            sleep_s = next_t - time.perf_counter()
            if sleep_s > 0:
                time.sleep(sleep_s)
            else:
                next_t = time.perf_counter()
                #logger.warning(f"Failing to maintain {self._rate_hz} Hz control loop, acheived {acheived_rate_hz} Hz.")

    def start_tracker(self):
        """Start the background streaming thread (idempotent)."""
        if self._tracker_thread and self._tracker_thread.is_alive():
            return
        self._tracker_stop.clear()
        self._tracker_thread = threading.Thread(
            target=self._tracker_loop, name=f"{self.name}-tracker", daemon=True
        )
        self._tracker_thread.start()

        # Set to track home position
        with self._tracker_lock:
            self._latest_target_deg = [
                self._canon_deg(a) for a in self._tracker_home_position_deg
            ]

        with self._tracker_lock:
            self._latest_gripper_target_pos = self._gripper_home_position

        logger.info("Started %s tracker @ %.1f Hz", self.name, self._rate_hz)

    def stop_tracker(self):
        """Stop the streaming thread and send zero velocities once."""
        if not self._tracker_thread:
            return
        self._tracker_stop.set()
        self._tracker_thread.join(timeout=2.0)
        self._tracker_thread = None
        try:
            if self.base is not None:
                self._send_joint_speeds_deg_s([0.0] * 7)
        except Exception:
            pass
        logger.info("Stopped %s tracker", self.name)

    # Helper Methods
    def _get_device_id(self):
        device_id = 0

        # Getting all device routing information (from DeviceManagerClient service)
        all_devices_info = self.device_manager.ReadAllDevices()

        device_handles = [
            hd
            for hd in all_devices_info.device_handle
            if hd.device_type == DeviceConfig_pb2.BASE
        ]
        if len(device_handles) == 0:
            print("Error: there is no base device registered in the devices info")
        elif len(device_handles) > 1:
            print(
                "Error: there are more than one base devices registered in the devices info"
            )
        else:
            handle = device_handles[0]
            device_id = handle.device_identifier
            print("Base found, device Id: {0}".format(device_id))

        return device_id

    def _canon_deg(self, a: float) -> float:
        # Always in range of [-180 to 180]
        return (a + 180.0) % 360.0 - 180.0

    def _angle_diff_deg(self, target: float, current: float) -> float:
        """
        Smallest signed angular difference (target - current) in degrees.
        Always in range [-180, +180].
        Example: target=359, current=1 -> -2 (deg).
        """
        diff = self._canon_deg(target - current)
        return diff

    def _read_joint_positions_deg(self) -> list[float]:
        """Return current joint positions [deg] (0..N-1) from cache."""
        with self._state_lock:
            return list(self._latest_joint_positions_deg)

    def _read_gripper_position(self) -> float | None:
        """Return current gripper position [0,1] from cache (None if unavailable)."""
        with self._state_lock:
            return float(self._latest_gripper_position)

    def _send_joint_speeds_deg_s(self, speeds: list[float]) -> None:
        joint_speeds = Base_pb2.JointSpeeds()
        for j, v in enumerate(speeds):
            js = joint_speeds.joint_speeds.add()
            js.joint_identifier = j
            js.value = float(v)   # deg/s
            js.duration = 0
        self.base.SendJointSpeedsCommand(joint_speeds)

    def _send_gripper_speed(self, speed_m11: float) -> None:
        s = float(speed_m11)
        s = max(-1.0, min(1.0, s)) # clamp to SDK expected input
        s = max(-self._gripper_max_speed, min(self._gripper_max_speed, s))

        cmd = Base_pb2.GripperCommand()
        cmd.mode = Base_pb2.GripperMode.GRIPPER_SPEED
        finger = cmd.gripper.finger.add()
        finger.finger_identifier = 0
        finger.value = s
        self.base.SendGripperCommand(cmd)

        self._last_gripper_speed_sent = s
        self._last_gripper_ts = time.perf_counter()   # ← rate check uses this
