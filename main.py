from aiohttp import web
import aiohttp_jinja2
from aiohttp_session import setup as session_setup
from aiohttp_session import SimpleCookieStorage
# from aiohttp_session import session_middleware
import aiohttp_session_flash
from aiohttp_session_flash import flash
import asyncio
# import base64
from datetime import datetime
from jinja2 import FileSystemLoader
import os.path as op
from wtforms import BooleanField
from wtforms import DateTimeField
from wtforms import Form
from wtforms import SelectField
from wtforms import StringField
from wtforms import SubmitField
from wtforms.validators import Length
from wtforms.validators import DataRequired

# from csrf_form import CsrfForm
from error import error_middleware
# from utils import generate_csrf_meta
from utils import remove_special_data

routes = web.RouteTableDef()


def get_channels():
    with open("/etc/channels.conf") as fichier:
        lignes = fichier.readlines()
    channels = [l.split(':', 1)[0] for l in lignes]
    return channels


def create_recording_task(loop, channel, program_filename, duration):
    command = f"/usr/bin/gnutv -channels /etc/channels.conf -out file {program_filename} -timeout {duration} \"{channel}\""
    process = asyncio.create_subprocess_shell(command)
    loop.create_task(process)


def record(channel, program_name, begin_date, end_date):
    loop = asyncio.get_running_loop()
    ref_time = loop.time()
    duration = (end_date - begin_date).total_seconds()
    starting_delay = (begin_date - datetime.now()).total_seconds()
    program_filename = program_name.replace(' ', '-') + ".ts"
    loop.call_at(ref_time + starting_delay, create_recording_task, loop, channel, program_filename, duration)



@routes.view("/", name="index")
@aiohttp_jinja2.template("index.html")
class IndexView(web.View):

    # class RecordForm(CsrfForm):
    class RecordForm(Form):
        channel = SelectField("Chaîne", coerce=int)
        program_name = StringField(
            "Nom du programme",
            validators=[DataRequired(), Length(min=5, max=128)],
            render_kw={"placeholder": "Entrez le nom du programme"}
        )
        immediate = BooleanField("Immédiat", default=False)
        begin_date = DateTimeField("Date de début", id="begin_date", format="%d-%m-%Y %H:%M")
        end_date = DateTimeField(
            "Date de fin",
            id="end_date",
            format="%d-%m-%Y %H:%M",
            validators=[DataRequired()]
        )
        submit = SubmitField("Valider")

    def __init__(self, request):
        super().__init__(request)
        self.channels_choices = list(enumerate(get_channels()))

    async def post(self):
        # form = RecordForm(await self.request.post(), meta=await generate_csrf_meta(self.request))
        form = RecordForm(await self.request.post())
        form.channel.choices = self.channels_choices
        if form.validate():
            data = remove_special_data(form.data)
            begin_date = data["begin_date"]
            end_date = data["end_date"]
            if begin_date >= end_date:
                flash(
                    self.request, (
                        "danger",
                        "La date de début doit être antérieure à la date de fin."
                    )
                )
            channel = self.channels_choices[data["channel"]][1]
            program_name = data["program_name"]
            record(channel, program_name, begin_date, end_date)
        else:
            flash(self.request, ("danger", "Le formulaire contient des erreurs."))
        return {"form": form}

    async def get(self,):
        # form = RecordForm(meta=await generate_csrf_meta(self.request))
        form = RecordForm()
        form.channel.choices = self.channels_choices
        return {"form": form}


if __name__ == "__main__":
    app = web.Application(middlewares=[error_middleware])
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

    web.run_app(app)
