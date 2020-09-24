from datetime import datetime
import logging
import os.path as op
import pickle

from aiohttp_babel.middlewares import _

from utils import set_locale
from utils import cancel_wakeup
from utils import wakeup

logger = logging.getLogger(__name__)

WAKEUPS_BIN_FILENAME = "wakeups.bin"
WAKEUPS_LOG_FILENAME = "wakeups.log"


class Wakeup:

    def __init__(self, config, path):
        self.wakeups = {}
        self.wakeups_filename = op.join(path, WAKEUPS_BIN_FILENAME)

        log_filename = op.join(path, WAKEUPS_LOG_FILENAME)
        logger.setLevel(logging.DEBUG)
        file_handler = logging.FileHandler(log_filename)
        formatter = logging.Formatter("%(asctime)s - %(message)s")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        self.id = 1

    def add_wakeup(self, date):
        self.wakeups[self.id] = date
        self.id += 1
        self.setup_wakeup()

    def cancel_wakeup(self, id_):
        if id_ in self.wakeups:
            del(self.wakeups[id_])
        self.setup_wakeup()

    def setup_wakeup(self):
        # remove expired wakeups
        now = datetime.now()
        wus = dict(filter(lambda x: x[1] > now, self.wakeups.items()))
        self.wakeups = wus

        if len(self.wakeups) == 0:
            logger.info(_("Annulation du réveil"))
            cancel_wakeup()
        else:
            # schedule the nearest wake up
            wu = sorted(self.wakeups.values())[0]

            logger.info(
                _("Programmation du réveil le {} à {} (id={})").format(
                    wu.strftime("%d/%m/%Y"), wu.strftime("%H:%M"), self.id
                )
            )
            wakeup(wu)

    @set_locale
    def save(self):
        with open(self.wakeups_filename, "wb") as f:
            pickle.dump(self.wakeups, f)

    @set_locale
    def load(self):
        """This function is executed outsite of a server request
        so we must simulate what does the babel middleware"""

        # wakeups
        try:
            with open(self.wakeups_filename, "rb") as f:
                wus = pickle.load(f)
        except FileNotFoundError:
            wus = {}

        for w in wus.values():
            self.add_wakeup(w)
