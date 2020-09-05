from aiohttp import web
import aiohttp_jinja2
from aiohttp_session import setup as session_setup
from aiohttp_session import SimpleCookieStorage
import aiohttp_session_flash
from aiohttp_session_flash import flash
import asyncio
from datetime import datetime
import os.path as op

from jinja2 import FileSystemLoader
from wtforms import DateTimeField
from wtforms import Form
from wtforms import SelectField
from wtforms import StringField
from wtforms import SubmitField
from wtforms.validators import Length
from wtforms.validators import DataRequired
from wtforms.validators import Optional

from error import error_middleware
from utils import read_configuration_file
from utils import remove_special_data

routes = web.RouteTableDef()


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


@routes.view("/", name="index")
@aiohttp_jinja2.template("index.html")
class IndexView(web.View):

    # class RecordForm(CsrfForm):
    class RecordForm(Form):
        adapter = SelectField("Enregistreur", coerce=int)
        channel = SelectField("Chaîne", coerce=int)
        program_name = StringField(
            "Nom du programme",
            validators=[DataRequired(), Length(min=5, max=128)],
            render_kw={"placeholder": "Entrez le nom du programme"}
        )
        begin_date = DateTimeField(
            "Date de début",
            id="begin_date",
            format="%d-%m-%Y %H:%M",
            validators=[Optional()]
        )
        end_date = DateTimeField(
            "Date de fin",
            id="end_date",
            format="%d-%m-%Y %H:%M",
            validators=[DataRequired()]
        )
        submit = SubmitField("Valider")

    def __init__(self, request):
        super().__init__(request)
        self.recorder = request.app.recorder
        self.adapters_choices = [(i, str(i)) for i in range(self.recorder.dvb_adapter_number)]
        self.channels_choices = list(enumerate(self.recorder.get_channels()))

    async def post(self):
        # form = self.RecordForm(await self.request.post(), meta=await generate_csrf_meta(self.request))
        form = self.RecordForm(await self.request.post())
        form.adapter.choices = self.adapters_choices
        form.channel.choices = self.channels_choices
        if form.validate():
            data = remove_special_data(form.data)

            error = False
            begin_date = data["begin_date"]
            if begin_date is None:
                begin_date = datetime.now()
            else:
                if begin_date <= datetime.now():
                    error = True
                    message = "La date de début doit être dans le futur."
            end_date = data["end_date"]
            if begin_date >= end_date:
                error = True
                message = "La date de début doit être antérieure à la date de fin."
            duration = (end_date - begin_date).total_seconds()
            if duration > int(self.recorder.max_duration):
                error = True
                message = "La durée de l'enregistrement est trop longue."
            if error:
                flash(self.request, ("danger", message))
            else:
                adapter = data["adapter"]
                channel = self.channels_choices[data["channel"]][1]
                program_name = data["program_name"]
                self.recorder.record(adapter, channel, program_name, begin_date, end_date, duration)
                message = (
                    f"L'enregistrement de \"{program_name}\" est programmé "
                    f"pour le {begin_date.strftime('%d/%m/%Y')} "
                    f"à {begin_date.strftime('%H:%M')} "
                    f"pendant {round(duration/60)} minutes de \"{channel}\" "
                    f"sur l'adaptateur {adapter}"
                )
                flash(self.request, ("info", message))
                return web.HTTPFound(self.request.app.router["index"].url_for())
        else:
            flash(self.request, ("danger", "Le formulaire contient des erreurs."))
        return {"form": form}

    async def get(self,):
        # form = RecordForm(meta=await generate_csrf_meta(self.request))
        form = self.RecordForm()
        form.adapter.choices = self.adapters_choices
        form.channel.choices = self.channels_choices
        return {"form": form}


if __name__ == "__main__":
    config = read_configuration_file()

    app = web.Application(middlewares=[error_middleware])

    app.recorder = Recorder(config["magneto"])

    session_setup(app, SimpleCookieStorage())
    app.middlewares.append(aiohttp_session_flash.middleware)

    template_dir = op.join(op.dirname(op.abspath(__file__)), "templates")
    aiohttp_jinja2.setup(
        app,
        loader=FileSystemLoader(template_dir),
        context_processors=(
            aiohttp_session_flash.context_processor,
        )
    )
    jinja2_env = aiohttp_jinja2.get_env(app)

    app.router.add_routes(routes)
    static_dir = op.join(op.dirname(op.abspath(__file__)), "static")
    app.router.add_static("/static", static_dir)

    web.run_app(app, port=int(config["network"]["port"]))
