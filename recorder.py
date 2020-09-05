import asyncio
from datetime import datetime
import os.path as op


class Recorder:
    id_ = 1

    def __init__(self, config):
        self.max_duration = int(config.get("max_duration", "18000"))
        self.dvb_adapter_number = int(config.get("dvb_adapter_number", "1"))
        self.channels_conf = config.get("channels_conf", "/etc/channels.conf")
        self.recording_directory = config.get("recording_directory", "/tmp")
        self.processes = [False] * self.dvb_adapter_number
        self.recordings = {}

    def get_channels(self):
        with open(self.channels_conf) as fichier:
            lines = fichier.readlines()
        channels = [l.split(':', 1)[0] for l in lines]
        return channels

    async def run_subprocess(self, command, adapter, id_):
        if not self.processes[adapter]:
            self.processes[adapter] = True
            process = await asyncio.create_subprocess_shell(command)
            self.recordings[id_]["handle"] = None
            self.recordings[id_]["process"] = process
            await process.wait()
            self.processes[adapter] = False
        del(self.recordings[id_])

    def make_command_and_run_it(self, loop, adapter, channel, program_filename,
                                duration, id_):
        filename = op.join(self.recording_directory, program_filename)
        command = (
            f"/usr/bin/gnutv -adapter {adapter} -channels {self.channels_conf} "
            f"-out file {filename} -timeout {duration} \"{channel}\""
        )
        loop.create_task(self.run_subprocess(command, adapter, id_))

    def record(self, adapter, channel, program_name, begin_date, end_date, duration):
        loop = asyncio.get_running_loop()
        program_filename = program_name.replace(' ', '-') + ".ts"
        handle = loop.call_later(
            (begin_date - datetime.now()).total_seconds(),
            self.make_command_and_run_it,
            loop,
            adapter,
            channel,
            program_filename,
            duration,
            self.id_
        )
        self.recordings[self.id_] = {
            "handle": handle,
            "process": None,
            "channel": channel,
            "program_name": program_name,
            "begin_date": begin_date,
            "end_date": end_date
        }
        self.id_ += 1

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
