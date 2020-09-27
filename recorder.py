import asyncio
from datetime import datetime
import logging
import os.path as op
import pickle

from aiohttp_babel.middlewares import _

from utils import set_locale

logger = logging.getLogger(__name__)

RECORDINGS_BIN_FILENAME = "recordings.bin"
RECORDINGS_LOG_FILENAME = "recordings.log"


class Recordings:
    def __init__(self, config, path):
        self.max_duration = int(config.get("max_duration", "18000"))
        self.dvb_adapter_number = int(config.get("dvb_adapter_number", "1"))
        self.channels_conf = config.get("channels_conf", "/etc/channels.conf")
        self.recording_directory = config.get("recording_directory", "/tmp")
        self.processes = [False] * self.dvb_adapter_number
        self.recordings = {}
        self.simulate = eval(config.get("simulate", "False"))
        self.recordings_filename = op.join(path, RECORDINGS_BIN_FILENAME)

        log_filename = op.join(path, RECORDINGS_LOG_FILENAME)
        logger.setLevel(logging.DEBUG)
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

    async def run_subprocess(self, command, adapter, id_):
        if self.processes[adapter]:
            logger.warning(_("Enregistreur occupé (id={})").format(id_))
        else:
            logger.debug(command)
            self.processes[adapter] = True
            process = await asyncio.create_subprocess_shell(command)
            self.recordings[id_]["handle"] = None
            self.recordings[id_]["process"] = process

            logger.debug(_("Début de l'enregistrement (id={})").format(id_))
            await process.wait()
            logger.debug(_("Fin de l'enregistrement (id={})").format(id_))

            self.processes[adapter] = False

            if self.recordings[id_]["shutdown"]:
                logger.debug(_("Mise hors tension (id={})").format(id_))
                process = await asyncio.create_subprocess_shell("sudo shutdown -h now")
                await process.wait()
        del(self.recordings[id_])

    def make_command_and_run_it(self, loop, adapter, channel, program_filename,
                                duration, id_):
        logger.info(_("Enregistrement de {} (id={})").format(program_filename, id_))

        if self.simulate:
            command = f"sleep {duration}"
        else:
            filename = op.join(self.recording_directory, program_filename)
            command = (
                f"/usr/bin/gnutv -adapter {adapter} -channels {self.channels_conf} "
                f"-out file {filename} -timeout {duration} \"{channel}\""
            )
        loop.create_task(self.run_subprocess(command, adapter, id_))

    def record(self, adapter, channel, program_name, immediate,
               begin_date, end_date, duration, shutdown):
        logger.info(
            _(
                "Programmation de l'enregistrement de \"{}\" "
                "pendant {} minutes de \"{}\" sur l'enregistreur {} (id={})"
            ).format(program_name, round(duration / 60), channel, adapter, self.id)
        )

        loop = asyncio.get_running_loop()
        program_filename = program_name.replace(' ', '-') + ".ts"
        if immediate:
            handle = loop.call_soon(
                self.make_command_and_run_it,
                loop,
                adapter,
                channel,
                program_filename,
                duration,
                self.id
            )
        else:
            handle = loop.call_later(
                (begin_date - datetime.now()).total_seconds(),
                self.make_command_and_run_it,
                loop,
                adapter,
                channel,
                program_filename,
                duration,
                self.id
            )
        self.recordings[self.id] = {
            "handle": handle,
            "process": None,
            "channel": channel,
            "program_name": program_name,
            "begin_date": begin_date,
            "end_date": end_date,
            "adapter": adapter,
            "shutdown": shutdown,
            "duration": duration
        }
        self.id += 1

    def cancel_recording(self, id_):
        if id_ in self.recordings:
            logger.info(_("Annulation de {} (id={})").format(
                self.recordings[id_]["program_name"], id_)
            )

            process = self.recordings[id_]["process"]
            if process is not None:
                process.terminate()

            handle = self.recordings[id_]["handle"]
            if handle is not None:
                handle.cancel()
                del(self.recordings[id_])

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

            for r in rec2.values():
                self.record(
                    r["adapter"],
                    r["channel"],
                    r["program_name"],
                    False,
                    r["begin_date"],
                    r["end_date"],
                    r["duration"],
                    r["shutdown"]
                )
