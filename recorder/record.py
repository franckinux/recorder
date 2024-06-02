import asyncio
from datetime import datetime
import logging
from pathlib import Path
import pickle

from aiohttp_babel.middlewares import _

import recorder.config as config
from recorder.utils import set_locale

logger = logging.getLogger(__name__)

RECORDINGS_BIN_FILENAME = "data/recordings.bin"


class Recorder:
    def __init__(self, path: Path):
        self.max_duration = config.general.max_duration
        self.dvb_adapter_number = config.general.dvb_adapter_number
        self.channels_conf = config.general.channels_conf
        self.recording_directory = config.general.recording_directory
        self.simulate = config.general.simulate
        self.busy = [False] * self.dvb_adapter_number
        self.recordings: dict[int, dict] = {}
        self.recordings_filename = Path(path, RECORDINGS_BIN_FILENAME)

        self.id = 1

    def get_recordings(self):
        """Returns recordings sorted by begin date"""
        return sorted(self.recordings.items(), key=lambda r: r[1]["begin_date"])

    def get_channels(self):
        with open(self.channels_conf) as fichier:
            lines = fichier.readlines()
        channels = [line.split(':', 1)[0] for line in lines]
        return channels

    async def record_program(
        self, delay: int, adapter: int, channel: str, filename: str,
        duration: int, shutdown, id_: int
    ):
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            del self.recordings[id_]
            return

        logger.info(_("Enregistrement de {} (id={})").format(filename, id_))

        if self.busy[adapter]:
            logger.warning(_("Enregistreur occupé (id={})").format(id_))
            return

        self.busy[adapter] = True

        logger.debug(_("Début de l'enregistrement (id={})").format(id_))
        if self.simulate:
            command = ("/usr/bin/sleep", str(int(duration)))
        else:
            record_filename = Path(self.recording_directory, filename)
            command = (
                "/usr/bin/dvbv5-zap",
                "-a", f"{adapter}",
                "-I", "zap",
                "-o", f"{record_filename}",
                "-c", f"{self.channels_conf}",
                "-t", f"{duration}",
                f"{channel}"
            )

        process = await asyncio.create_subprocess_exec(*command)
        logger.debug(f"process id: {process.pid}")
        self.recordings[id_]["process"] = process
        await process.wait()

        logger.debug(f"process return code: {process.returncode}")
        logger.debug(_("Fin de l'enregistrement (id={})").format(id_))

        self.busy[adapter] = False
        del self.recordings[id_]

        if process.returncode != 0 and not self.simulate:
            logger.debug(f"delete file {record_filename.name}")
            record_filename.unlink()
            return

        if shutdown:
            logger.debug(_("Mise hors tension (id={})").format(id_))
            await asyncio.create_subprocess_shell(
                "sudo shutdown -h now",
                shell=True,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )

    async def record(
        self, adapter: int, channel: str, program_name: str, immediate: bool,
        begin_date: datetime, end_date: datetime, duration: int, shutdown: bool
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
            delay = int((begin_date - datetime.now()).total_seconds())
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
            "channel": channel,
            "program_name": program_name,
            "begin_date": begin_date,
            "end_date": end_date,
            "adapter": adapter,
            "shutdown": shutdown,
            "duration": duration,
            "process": None,
            "task": task
        }

        self.id += 1

    async def cancel_recording(self, id_):
        if id_ in self.recordings:
            logger.info(_("Annulation de {} (id={})").format(
                self.recordings[id_]["program_name"], id_)
            )

            process = self.recordings[id_]["process"]
            if process is not None:
                process.terminate()
            else:
                self.recordings[id_]["task"].cancel()
            await self.recordings[id_]["task"]

    async def cancel_recordings(self):
        for id_ in list(self.recordings.keys()):
            record = self.recordings[id_]
            process = record["process"]
            if process is not None:
                process.terminate()
            else:
                record["task"].cancel()
            await record["task"]

    @set_locale
    async def save(self):
        """Saves the recordings to a file"""
        # only recordings not started
        now = datetime.now()
        recordings = dict(
            filter(lambda e: e[1]["begin_date"] > now, self.recordings.items())
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
