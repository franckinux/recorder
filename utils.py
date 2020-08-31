import configparser
import os
import sys

# from aiohttp_babel.middlewares import _
from aiohttp_session import get_session
# from babel.support import LazyProxy


def remove_special_data(dico):
    # del dico["csrf_token"]
    del dico["submit"]
    return dico


# async def generate_csrf_meta(request):
#     return {
#         "csrf_context": await get_session(request),
#         "csrf_secret": request.app["config"]["application"]["secret_key"].encode("ascii")
#     }


# def lazy_gettext(s):
#     return LazyProxy(_, s, enable_cache=False)
#
#
# _l = lazy_gettext


def read_configuration_file():
    config = configparser.ConfigParser()
    try:
        conf_filename = os.environ.get("MAGNETO_CONFIG")
        config.read(conf_filename)
    except Exception:
        sys.stderr.write(
            "problem encountered while reading the configuration file %s\n" %
            conf_filename
        )
        return None
    return config


def write_configuration_file(config):
    conf_filename = os.environ.get("MAGNETO_CONFIG")

    with open(conf_filename, "w") as f:
        config.write(f)
