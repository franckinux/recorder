import configparser
import os
import os.path as op
import sys

# from aiohttp_babel.middlewares import _
# from babel.support import LazyProxy


def remove_special_data(dico):
    # del dico["csrf_token"]
    del dico["submit"]
    return dico


# def lazy_gettext(s):
#     return LazyProxy(_, s, enable_cache=False)
#
#
# _l = lazy_gettext


def read_configuration_file(path):
    default_config_filename = op.join(path, "config.ini")
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


def write_configuration_file(path, config):
    default_config_filename = op.join(path, "config.ini")
    conf_filename = os.environ.get("RECORDER_CONFIG", default_config_filename)

    with open(conf_filename, "w") as f:
        config.write(f)
