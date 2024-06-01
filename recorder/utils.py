import asyncio
import os
from pathlib import Path

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


async def run(command: tuple, timeout: int = 0):
    try:
        process = await asyncio.create_subprocess_exec(*command)
        if timeout == 0:
            await process.wait()
        else:
            await asyncio.wait_for(process.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        process.terminate()
        await process.wait()
