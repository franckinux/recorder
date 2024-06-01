import logging
from pathlib import Path

import tomli

from recorder.typem import GeneralConfig

general = None

loggers = {}

_module = []


def parse_log_config(data: dict):
    global loggers
    global _module

    for k, v in data.items():
        _module.append(k)
        try:
            loggers[".".join(_module)] = getattr(logging, v["level"])
            _module.pop()
        except KeyError:
            parse_log_config(v)


def read(config_filename: str):
    config_file = Path(config_filename)
    with open(config_file, "rb") as f:
        raw_config = tomli.load(f)

    global general
    general = GeneralConfig(**raw_config["general"])

    global loggers
    parse_log_config(raw_config["logger"][0])
