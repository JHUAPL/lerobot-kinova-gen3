import logging
import time
from typing import Any

from ..so101_leader.so101_leader import SO101Leader
from ..teleoperator import Teleoperator
from .config_kinova_gen3_so101_leader import KinovaGen3So101LeaderConfig

logger = logging.getLogger(__name__)


class KinovaGen3So101Leader(SO101Leader):

    config_class = KinovaGen3So101LeaderConfig
    name = "kinova_gen3_so101_leader"

    def __init__(self, config: KinovaGen3So101LeaderConfig):
        super().__init__(config)
        self.config = config
        self._is_connected = False

    @property
    def action_features(self) -> dict:
        """
        A dictionary describing the structure and types of the actions produced by the teleoperator. Its
        structure (keys) should match the structure of what is returned by :pymeth:`get_action`. Values for
        the dict should be the type of the value if it's a simple value, e.g. `float` for single
        proprioceptive value (a joint's goal position/velocity)

        Note: this property should be able to be called regardless of whether the robot is connected or not.
        """
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
    def feedback_features(self) -> dict:
        """
        A dictionary describing the structure and types of the feedback actions expected by the robot. Its
        structure (keys) should match the structure of what is passed to :pymeth:`send_feedback`. Values for
        the dict should be the type of the value if it's a simple value, e.g. `float` for single
        proprioceptive value (a joint's goal position/velocity)

        Note: this property should be able to be called regardless of whether the robot is connected or not.
        """
        return {}

    def get_action(self) -> dict[str, Any]:
        """
        Retrieve the current action from the teleoperator.

        Returns:
            dict[str, Any]: A flat dictionary representing the teleoperator's current actions. Its
                structure should match :pymeth:`observation_features`.
        """

        start = time.perf_counter()

        # Read the SO101 leader.
        leader_action: dict[str, float] = self.bus.sync_read("Present_Position")
        leader_action = {f"{motor}.pos": val for motor, val in leader_action.items()}
        # Reference for what leader_action looks like
        # leader_action = {
        #        "shoulder_pan.pos": float,
        #        "shoulder_lift.pos": float,
        #        "elbow_flex.pos": float,
        #        "wrist_flex.pos": float,
        #        "wrist_roll.pos": float,
        #        "gripper.pos": float,
        #    }

        # TODO: make flexible to use radians as well, and test
        if not self.config.use_degrees:
            logger.error(
                f"{self.name} only currently supports degrees. Set use_degrees=True in configuration."
            )
            raise ValueError(
                f"{self.name} only currently supports degrees. Set use_degrees=True in configuration."
            )

        # offsets/signs to reconcile kinematics and make teleop intuitive.
        # May be value in tweaking these to account for differenct in robot segment lengths
        offsets = {
            "shoulder_pan.pos": 0.0,
            #"shoulder_lift.pos": 0.0,
            "shoulder_lift.pos": 20.0,
            "elbow_flex.pos": 90.0,
            #"wrist_flex.pos": 0.0,
            "wrist_flex.pos": -20.0,
            #"wrist_roll.pos": 180,
            "wrist_roll.pos": 0,
            "gripper.pos": -100.0,
        }
        signs = {
            "shoulder_pan.pos": +1.0,
            "shoulder_lift.pos": +1.0,
            "elbow_flex.pos": -1.0,
            "wrist_flex.pos": -1.0,
            "wrist_roll.pos": +1.0,
            "gripper.pos": -0.01, # Range of 0-1 instead of 0-100
        }

        #  Map SO101 leader DOFs → Kinova Gen3 joints (example mapping).
        # Fill in/adjust as your teleop ergonomics demand.
        def map_joints(k):  # leader helper with safety defaults
            return float(signs[k] * (leader_action.get(k) + offsets[k]))

        action = {
            "joint_id_0.pos": map_joints("shoulder_pan.pos"),  # base yaw
            #"joint_id_1.pos": 15.0, # L("shoulder_lift.pos"),  # shoulder
            "joint_id_1.pos": map_joints("shoulder_lift.pos"),  # shoulder
            "joint_id_2.pos": 180.0,  # doesn't have corresponding joint
            #"joint_id_3.pos": 230, # L("elbow_flex.pos"),
            "joint_id_3.pos": map_joints("elbow_flex.pos"),
            "joint_id_4.pos": 0.0, # doesn't have corresponding joint
            #"joint_id_5.pos": 55.0, # L("wrist_flex.pos"),
            "joint_id_5.pos": map_joints("wrist_flex.pos"),
            #"joint_id_6.pos": 90, # L("wrist_roll.pos"),
            "joint_id_6.pos": map_joints("wrist_roll.pos"),
            "gripper.pos": map_joints("gripper.pos"),
        }

        dt_ms = (time.perf_counter() - start) * 1e3
        logger.debug(f"{self} read action: {dt_ms:.1f}ms")
        return action
