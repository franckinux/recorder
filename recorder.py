import asyncio
from datetime import datetime
import logging
import os
import os.path as op

from aiohttp_babel.middlewares import _

logger = logging.getLogger(__name__)


class Recorder:
    def __init__(self, config, path):
        self.max_duration = int(config.get("max_duration", "18000"))
        self.dvb_adapter_number = int(config.get("dvb_adapter_number", "1"))
        self.channels_conf = config.get("channels_conf", "/etc/channels.conf")
        self.recording_directory = config.get("recording_directory", "/tmp")
        self.processes = [False] * self.dvb_adapter_number
        self.recordings = {}

        default_log_filename = op.join(path, "recorder.log")
        log_filename = os.environ.get("RECORDER_LOG", default_log_filename)
        logger.setLevel(logging.DEBUG)
        file_handler = logging.FileHandler(log_filename)
        formatter = logging.Formatter("%(asctime)s - %(message)s")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        self.id = 1

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
                process = await asyncio.create_subprocess_shell("shutdown -h now")
                await process.wait()
        del(self.recordings[id_])

    def make_command_and_run_it(self, loop, adapter, channel, program_filename,
                                duration, id_):
        logger.info(_("Enregistrement de {} (id={})").format(program_filename, id_))

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
            ).format(program_name, round(duration / 60, channel, adapter, self.id))
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
            "shutdown": shutdown
        }
        self.id += 1

    def get_recordings(self):
        return self.recordings

    def cancel_recording(self, id_):
        if id_ in self.recordings:
            handle = self.recordings[id_]["handle"]
            if handle is not None:
                handle.cancel()
            process = self.recordings[id_]["process"]
            if process is not None:
                process.terminate()
            del(self.recordings[id_])
