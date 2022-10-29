import asyncio
from datetime import datetime
import logging
from pathlib import Path
import pickle

from aiohttp_babel.middlewares import _

from utils import set_locale

logger = logging.getLogger(__name__)

RECORDINGS_BIN_FILENAME = "data/recordings.bin"
RECORDINGS_LOG_FILENAME = "logs/recordings.log"


class Recordings:
    def __init__(self, config, path: Path):
        self.max_duration = int(config.get("max_duration", "18000"))
        self.dvb_adapter_number = int(config.get("dvb_adapter_number", "1"))
        self.channels_conf = config.get("channels_conf", "/etc/channels.conf")
        self.recording_directory = config.get("recording_directory", "/tmp")
        self.busy = [False] * self.dvb_adapter_number
        self.recordings = {}
        self.simulate = eval(config.get("simulate", "False"))
        self.recordings_filename = Path(path, RECORDINGS_BIN_FILENAME)

        log_level = config.get("log_level", "INFO")
        log_level = getattr(logging, log_level)

        log_filename = Path(path, RECORDINGS_LOG_FILENAME)
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

    async def run(self, command: tuple, timeout: int = 0):
        try:
            process = await asyncio.create_subprocess_exec(*command)
            if timeout == 0:
                await process.wait()
            else:
                await asyncio.wait_for(process.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            process.terminate()
            await process.wait()

    async def record_program(
        self, delay, adapter, channel, filename: str, duration, shutdown, id_
    ):
        await asyncio.sleep(delay)

        logger.info(_("Enregistrement de {} (id={})").format(filename, id_))
        self.recordings[id_]["recording"] = True

        if self.busy[adapter]:
            logger.warning(_("Enregistreur occupé (id={})").format(id_))
        else:
            self.busy[adapter] = True

            if self.simulate:
                await asyncio.sleep(duration)
            else:
                logger.debug(_("Début de l'enregistrement (id={})").format(id_))

                filename = Path(self.recording_directory, filename)
                command = (
                    "/usr/bin/dvbv5-zap",
                    "-a", f"{adapter}",
                    "-I", "zap",
                    "-o", f"{filename}",
                    "-c", f"{self.channels_conf}",
                    "-t", f"{duration}",
                    f"{channel}"
                )
                await self.run(command)

                logger.debug(_("Fin de l'enregistrement (id={})").format(id_))

            self.busy[adapter] = False
            del self.recordings[id_]

            if shutdown:
                logger.debug(_("Mise hors tension (id={})").format(id_))
                await asyncio.create_subprocess_shell(
                    "sudo shutdown -h now",
                    shell=True,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL
                )

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
        asyncio.create_task(
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
            "channel": channel,
            "program_name": program_name,
            "begin_date": begin_date,
            "end_date": end_date,
            "adapter": adapter,
            "shutdown": shutdown,
            "duration": duration,
            "recording": False
        }
        self.id += 1

    async def cancel_recording(self, id_):
        if id_ in self.recordings:
            logger.info(_("Annulation de {} (id={})").format(
                self.recordings[id_]["program_name"], id_)
            )

            if not self.recordings[id_]["recording"]:
                del self.recordings[id_]

    @set_locale
    async def save(self):
        """Saves the recordings from a file"""
        # only recordings not started
        recordings = dict(
            filter(lambda e: not e[1]["recording"], self.recordings.items())
        )

        with open(self.recordings_filename, "wb") as f:
            pickle.dump(recordings, f)

    @set_locale
    async def load(self):
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

            for r in rec2.values():
                await self.record(
                    r["adapter"],
                    r["channel"],
                    r["program_name"],
                    False,
                    r["begin_date"],
                    r["end_date"],
                    r["duration"],
                    r["shutdown"]
                )
