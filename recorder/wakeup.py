from datetime import datetime
import logging
from pathlib import Path
import pickle

from aiohttp_babel.middlewares import _

from recorder.utils import set_locale
from recorder.utils import cancel_awakening
from recorder.utils import schedule_awakening

logger = logging.getLogger(__name__)

AWAKENINGS_BIN_FILENAME = "data/awakenings.bin"


class Awakenings:

    def __init__(self, path: Path):
        self.awakenings = {}
        self.awakenings_filename = Path(path, AWAKENINGS_BIN_FILENAME)

        self.id = 1

    def get_awakenings(self):
        """Returns awakenings sorted by date"""
        return sorted(self.awakenings.items(), key=lambda w: w[1])

    def add_awakening(self, date):
        logger.info(
            _("Ajout du réveil le {} à {} (id={})").format(
                date.strftime("%d/%m/%Y"), date.strftime("%H:%M"), self.id
            )
        )
        self.awakenings[self.id] = date
        self.id += 1
        self.setup_awakening()

    def cancel_awakening(self, id_):
        if id_ in self.awakenings:
            logger.info(_("Suppression du réveil (id={})").format(id_))
            del self.awakenings[id_]
            self.setup_awakening()

    def setup_awakening(self):
        # remove expired awakenings
        now = datetime.now()
        wus = dict(filter(lambda x: x[1] > now, self.awakenings.items()))
        self.awakenings = wus

        if len(self.awakenings) == 0:
            logger.info(_("Annulation du réveil"))
            # utils function, not the method of this class !
            cancel_awakening()
        else:
            # select the nearest awakening...
            wui, wut = sorted(self.awakenings.items(), key=lambda w: w[1])[0]

            logger.info(
                _("Programmation du réveil le {} à {} (id={})").format(
                    wut.strftime("%d/%m/%Y"), wut.strftime("%H:%M"), wui
                )
            )
            # ...and schedule it
            schedule_awakening(wut)

    @set_locale
    async def save(self):
        """Saves the awakenings to a file"""
        with open(self.awakenings_filename, "wb") as f:
            pickle.dump(self.awakenings, f)

    @set_locale
    async def load(self):
        """Loads the awakenings from a file"""

        # awakenings
        try:
            with open(self.awakenings_filename, "rb") as f:
                wus = pickle.load(f)
        except FileNotFoundError:
            wus = {}

        if len(wus) == 0:
            self.setup_awakening()
        else:
            for w in wus.values():
                self.add_awakening(w)
