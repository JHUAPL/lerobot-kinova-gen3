from dataclasses import dataclass

from ..config import TeleoperatorConfig


@TeleoperatorConfig.register_subclass("kinova_gen3_teleop_no_op")
@dataclass
class KinovaGen3TeleopNoOpConfig(TeleoperatorConfig):
    # Port to connect to the arm
    dummy_attribute: int = 1
