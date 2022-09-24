import asyncio
from datetime import datetime
import logging
import os.path as op
import pickle

from aiohttp_babel.middlewares import _

from utils import set_locale

logger = logging.getLogger(__name__)

RECORDINGS_BIN_FILENAME = "data/recordings.bin"
RECORDINGS_LOG_FILENAME = "logs/recordings.log"


class Recordings:
    def __init__(self, config, path):
        self.max_duration = int(config.get("max_duration", "18000"))
        self.dvb_adapter_number = int(config.get("dvb_adapter_number", "1"))
        self.channels_conf = config.get("channels_conf", "/etc/channels.conf")
        self.recording_directory = config.get("recording_directory", "/tmp")
        self.busy = [False] * self.dvb_adapter_number
        self.recordings = {}
        self.simulate = eval(config.get("simulate", "False"))
        self.recordings_filename = op.join(path, RECORDINGS_BIN_FILENAME)

        log_level = config.get("log_level", "INFO")
        log_level = getattr(logging, log_level)

        log_filename = op.join(path, RECORDINGS_LOG_FILENAME)
        logger.setLevel(log_level)
        file_handler = logging.FileHandler(log_filename)
        formatter = logging.Formatter("%(asctime)s - %(message)s")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        self.id = 1

    def get_recordings(self):
        """Returns recordings sorted by begin date"""
        return sorted(self.recordings.items(), key=lambda r: r[1]["begin_date"])

    def get_channels(self):
        with open(self.channels_conf) as fichier:
            lines = fichier.readlines()
        channels = [l.split(':', 1)[0] for l in lines]
        return channels

    async def record_program(
        self, delay, adapter, channel, program_filename, duration, shutdown, id_
    ):
        await asyncio.sleep(delay)

        logger.info(_("Enregistrement de {} (id={})").format(program_filename, id_))

        if self.busy[adapter]:
            logger.warning(_("Enregistreur occupé (id={})").format(id_))
        else:
            self.busy[adapter] = True

            cancelled = False
            try:
                if self.simulate:
                    await asyncio.sleep(delay)
                else:
                    await asyncio.to_thread(
                        f"/usr/bin/tzap -x -a {adapter} -r \"channel\""
                    )

                    logger.debug(_("Début de l'enregistrement (id={})").format(id_))
                    dev = "/etc/dvb/adapter{adapter}/dvr0"
                    filename = op.join(self.recording_directory, program_filename)
                    await asyncio.to_thread(f"cat {dev} > {filename}")
                    logger.debug(_("Fin de l'enregistrement (id={})").format(id_))
            except asyncio.CancelledError:
                cancelled = True

            self.busy[adapter] = False
            del self.recordings[id_]

            if shutdown and not cancelled:
                logger.debug(_("Mise hors tension (id={})").format(id_))
                await asyncio.to_thread("sudo shutdown -h now")

    async def record(
        self, adapter, channel, program_name, immediate,
        begin_date, end_date, duration, shutdown
    ):
        logger.info(
            _(
                "Programmation de l'enregistrement de \"{}\" "
                "pendant {} minutes de \"{}\" sur l'enregistreur {} (id={})"
            ).format(program_name, round(duration / 60), channel, adapter, self.id)
        )

        program_filename = program_name.replace(' ', '-') + ".ts"
        if immediate:
            delay = 0
        else:
            delay = (begin_date - datetime.now()).total_seconds()
        task = asyncio.create_task(
            self.record_program(
                delay,
                adapter,
                channel,
                program_filename,
                duration,
                shutdown,
                self.id
            )
        )

        self.recordings[self.id] = {
            "task": task,
            "channel": channel,
            "program_name": program_name,
            "begin_date": begin_date,
            "end_date": end_date,
            "adapter": adapter,
            "shutdown": shutdown,
            "duration": duration
        }
        self.id += 1

    async def cancel_recording(self, id_):
        if id_ in self.recordings:
            logger.info(_("Annulation de {} (id={})").format(
                self.recordings[id_]["program_name"], id_)
            )

            task = self.recordings[id_]["task"]
            if task is not None:
                task.cancel()
                await task
                del self.recordings[id_]

    @set_locale
    def save(self):
        """Saves the recordings from a file"""
        # only recordings not started
        recordings = dict(
            filter(lambda e: e[1]["process"] is None, self.recordings.items())
        )
        for v in recordings.values():
            v["handle"] = None

        with open(self.recordings_filename, "wb") as f:
            pickle.dump(recordings, f)

    @set_locale
    def load(self):
        """Loads the recordings from a file"""

        try:
            with open(self.recordings_filename, "rb") as f:
                rec1 = pickle.load(f)
        except FileNotFoundError:
            rec1 = {}

        if len(rec1) != 0:
            # only recordings not expired
            now = datetime.now()
            rec2 = dict(
                filter(lambda e: e[1]["begin_date"] > now, rec1.items())
            )

            loop = asyncio.get_event_loop()
            for r in rec2.values():
                loop.call(
                    self.record,
                    r["adapter"],
                    r["channel"],
                    r["program_name"],
                    False,
                    r["begin_date"],
                    r["end_date"],
                    r["duration"],
                    r["shutdown"]
                )
