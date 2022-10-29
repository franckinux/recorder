import configparser
import os
from pathlib import Path
import sys

from aiohttp_babel import locale
from aiohttp_babel.middlewares import _
from aiohttp_babel.middlewares import _thread_locals
from babel.support import LazyProxy


_language_code = None


def set_language(lang):
    global _language_code
    _language_code = lang


def remove_special_data(dico):
    dct = dict(dico)
    for k in dico.keys():
        if k.startswith("submit") or k in ["csrf"]:
            del dct[k]
    return dct


def lazy_gettext(s):
    return LazyProxy(_, s, enable_cache=False)


_l = lazy_gettext


def set_locale(function):
    """This is a decorator that simulates babel middleware behavior. It is
    useful when the function is not executed in a request handler."""

    async def wrapper(*args, **kwargs):
        _thread_locals.locale = locale.get(_language_code)
        await function(*args, **kwargs)

    return wrapper


def read_configuration_file(path: Path):
    default_config_filename = Path(path, "config.ini")
    config = configparser.ConfigParser()
    try:
        conf_filename = os.environ.get("RECORDER_CONFIG", default_config_filename)
        config.read(conf_filename)
    except Exception:
        sys.stderr.write(
            "problem encountered while reading the configuration file %s\n" %
            conf_filename
        )
        return None
    return config


def write_configuration_file(path: Path, config):
    default_config_filename = Path(path, "config.ini")
    conf_filename = os.environ.get("RECORDER_CONFIG", default_config_filename)

    with open(conf_filename, "w") as f:
        config.write(f)


def halt():
    os.system("sudo shutdown -h now")


def schedule_awakening(date):
    os.system(f"sudo rtcwake -m no -u -t {date.strftime('%s')}")


def cancel_awakening():
    os.system("sudo rtcwake -m disable")
