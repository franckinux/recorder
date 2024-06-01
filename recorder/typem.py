from dataclasses import dataclass
# from enum import auto
# from enum import Enum
# from enum import IntEnum


@dataclass
class GeneralConfig:
    dvb_adapter_number: int
    channels_conf: str
    max_duration: int
    recording_directory: str
    language: str
    simulate: bool
    port: int
