import logging
import time
from typing import Any

from ..teleoperator import Teleoperator
from .config_kinova_gen3_teleop_no_op import KinovaGen3TeleopNoOpConfig

logger = logging.getLogger(__name__)


class KinovaGen3TeleopNoOp(Teleoperator):

    config_class = KinovaGen3TeleopNoOpConfig
    name = "kinova_gen3_teleop_no_op"

    def __init__(self, config: KinovaGen3TeleopNoOpConfig):
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

    @property
    def is_connected(self) -> bool:
        """
        Whether the teleoperator is currently connected or not. If `False`, calling :pymeth:`get_action`
        or :pymeth:`send_feedback` should raise an error.
        """
        return self._is_connected

    def connect(self, calibrate: bool = True) -> None:
        """
        Establish communication with the teleoperator.

        Args:
            calibrate (bool): If True, automatically calibrate the teleoperator after connecting if it's not
                calibrated or needs calibration (this is hardware-dependant).
        """
        self._is_connected = True

    @property
    def is_calibrated(self) -> bool:
        """Whether the teleoperator is currently calibrated or not. Should be always `True` if not applicable"""
        return True

    def calibrate(self) -> None:
        """
        Calibrate the teleoperator if applicable. If not, this should be a no-op.

        This method should collect any necessary data (e.g., motor offsets) and update the
        :pyattr:`calibration` dictionary accordingly.
        """
        pass

    def configure(self) -> None:
        """
        Apply any one-time or runtime configuration to the teleoperator.
        This may include setting motor parameters, control modes, or initial state.
        """
        pass

    def get_action(self) -> dict[str, Any]:
        """
        Retrieve the current action from the teleoperator.

        Returns:
            dict[str, Any]: A flat dictionary representing the teleoperator's current actions. Its
                structure should match :pymeth:`observation_features`.
        """
        action_dict = {
            "joint_id_0.pos": 0.0,
            "joint_id_1.pos": 0.0,
            "joint_id_2.pos": 0.0,
            "joint_id_3.pos": 0.0,
            "joint_id_4.pos": 0.0,
            "joint_id_5.pos": 0.0,
            "joint_id_6.pos": 0.0,
            "gripper.pos": 0.0,
        }
        return action_dict

    def send_feedback(self, feedback: dict[str, Any]) -> None:
        """
        Send a feedback action command to the teleoperator.

        Args:
            feedback (dict[str, Any]): Dictionary representing the desired feedback. Its structure should match
                :pymeth:`feedback_features`.

        Returns:
            dict[str, Any]: The action actually sent to the motors potentially clipped or modified, e.g. by
                safety limits on velocity.
        """
        pass

    def disconnect(self) -> None:
        """Disconnect from the teleoperator and perform any necessary cleanup."""
        self._is_connected = False
