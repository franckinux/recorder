from datetime import datetime
from functools import partial
import os.path as op

from aiohttp import web
from aiohttp_babel.locale import load_gettext_translations
from aiohttp_babel.locale import set_default_locale
from aiohttp_babel.locale import set_locale_detector
from aiohttp_babel.middlewares import _
from aiohttp_babel.middlewares import babel_middleware
import aiohttp_jinja2
from aiohttp_session import setup as session_setup
from aiohttp_session import SimpleCookieStorage
import aiohttp_session_flash
from aiohttp_session_flash import flash
from jinja2 import FileSystemLoader
from wtforms import BooleanField
from wtforms import DateTimeField
from wtforms import Form
from wtforms import SelectField
from wtforms import StringField
from wtforms import SubmitField
from wtforms.validators import Length
from wtforms.validators import DataRequired
from wtforms.validators import Optional

from error import error_middleware
from recorder import Recordings
from utils import _l
from utils import read_configuration_file
from utils import remove_special_data
from utils import set_language
from utils import halt
from wakeup import Awakenings

routes = web.RouteTableDef()

DEFAULT_LANGUAGE = "fr"


def locale_detector(request, locale):
    return locale


def setup_i18n(path, locale):
    set_default_locale(DEFAULT_LANGUAGE)
    locales_dir = op.join(path, "locales", "translations")
    load_gettext_translations(locales_dir, "messages")

    partial_locale_detector = partial(locale_detector, locale=locale)
    set_locale_detector(partial_locale_detector)


async def cleanup(app):
    await app.recorder.save()
    await app.wakeup.save()


async def startup(app):
    await app.recorder.load()
    await app.wakeup.load()


@aiohttp_jinja2.template("index.html")
async def cancel_recording(request):
    id_ = int(request.match_info["id"])
    await request.app.recorder.cancel_recording(id_)
    return web.HTTPFound(request.app.router["index"].url_for())


@aiohttp_jinja2.template("index.html")
async def cancel_awakening(request):
    id_ = int(request.match_info["id"])
    request.app.wakeup.cancel_awakening(id_)
    return web.HTTPFound(request.app.router["index"].url_for())


@routes.view("/", name="index")
@aiohttp_jinja2.template("index.html")
class IndexView(web.View):

    class RecordingForm(Form):
        adapter = SelectField(_l("Enregistreur"), coerce=int)
        channel = SelectField(_l("Chaîne"), coerce=int)
        program_name = StringField(
            _l("Nom du programme"),
            validators=[DataRequired(), Length(min=5, max=128)],
            render_kw={"placeholder": _l("Entrez le nom du programme")}
        )
        begin_date = DateTimeField(
            _l("Date de début"),
            id="begin_date",
            format="%d/%m/%Y %H:%M",
            validators=[Optional()]
        )
        end_date = DateTimeField(
            _l("Date de fin"),
            id="end_date",
            format="%d/%m/%Y %H:%M",
            validators=[DataRequired()]
        )
        shutdown = BooleanField(_l("Extinction"))
        submit = SubmitField(_l("Valider"))

    class AwakeningForm(Form):
        awakening_date = DateTimeField(
            _l("Date de réveil"),
            id="awakening_date",
            format="%d/%m/%Y %H:%M",
            validators=[DataRequired()]
        )
        submit2 = SubmitField(_l("Valider"))

    class ToolsForm(Form):
        shutdown = BooleanField(_l("Extinction"))
        submit3 = SubmitField(_l("Valider"))

    def __init__(self, request):
        super().__init__(request)
        self.recorder = request.app.recorder
        self.wakeup = request.app.wakeup
        self.adapters_choices = [(i, str(i)) for i in range(self.recorder.dvb_adapter_number)]
        self.channels_choices = list(enumerate(self.recorder.get_channels()))

    async def post(self):
        form = self.RecordingForm(await self.request.post())
        form.adapter.choices = self.adapters_choices
        form.channel.choices = self.channels_choices
        if form.data["submit"]:
            if form.validate():
                data = remove_special_data(form.data)

                error = False
                begin_date = data["begin_date"]
                if begin_date is None:
                    immediate = True
                    begin_date = datetime.now()
                else:
                    immediate = False
                    if begin_date <= datetime.now():
                        error = True
                        message = _("La date de début doit être dans le futur.")
                end_date = data["end_date"]
                if begin_date >= end_date:
                    error = True
                    message = _("La date de début doit être antérieure à la date de fin.")
                duration = (end_date - begin_date).total_seconds()
                if duration > int(self.recorder.max_duration):
                    error = True
                    message = _("La durée de l'enregistrement est trop longue.")
                if error:
                    flash(self.request, ("danger", message))
                else:
                    adapter = data["adapter"]
                    shutdown = data["shutdown"]
                    channel = self.channels_choices[data["channel"]][1]
                    program_name = data["program_name"]
                    await self.recorder.record(
                        adapter, channel, program_name, immediate,
                        begin_date, end_date, duration, shutdown
                    )
                    message = _(
                        "L'enregistrement de \"{}\" est programmé "
                        "pour le {} à {} pendant {} minutes de \"{}\" "
                        "sur l'enregistreur {}"
                    ).format(
                        program_name, begin_date.strftime("%d/%m/%Y"),
                        begin_date.strftime("%H:%M"), round(duration / 60),
                        channel, adapter
                    )
                    flash(self.request, ("info", message))
                    return web.HTTPFound(self.request.app.router["index"].url_for())
            else:
                flash(self.request, ("danger", _("Le formulaire contient des erreurs.")))

        form2 = self.AwakeningForm(await self.request.post())
        if form2.data["submit2"]:
            if form2.validate():
                data = remove_special_data(form2.data)
                awakening_date = data["awakening_date"]
                self.wakeup.add_awakening(awakening_date)
                return web.HTTPFound(self.request.app.router["index"].url_for())
            else:
                flash(self.request, ("danger", _("Le formulaire contient des erreurs.")))

        form3 = self.ToolsForm(await self.request.post())
        if form3.data["submit3"]:
            if form3.validate():
                data = remove_special_data(form3.data)
                if data["shutdown"]:
                    halt()
            else:
                flash(self.request, ("danger", _("Le formulaire contient des erreurs.")))

        return {
            "form": form, "recordings": self.recorder.get_recordings(),
            "form2": form2, "awakenings": self.wakeup.get_awakenings(),
            "form3": form3
        }

    async def get(self,):
        form = self.RecordingForm()
        form.adapter.choices = self.adapters_choices
        form.channel.choices = self.channels_choices

        form2 = self.AwakeningForm()
        form3 = self.ToolsForm()

        return {
            "form": form, "recordings": self.recorder.get_recordings(),
            "form2": form2, "awakenings": self.wakeup.get_awakenings(),
            "form3": form3
        }


if __name__ == "__main__":
    path = op.dirname(op.abspath(__file__))

    config = read_configuration_file(path)

    lang = config["recorder"].get("language", DEFAULT_LANGUAGE)
    set_language(lang)
    setup_i18n(path, lang)

    app = web.Application(middlewares=[error_middleware, babel_middleware])

    app.recorder = Recordings(config["recorder"], path)
    app.wakeup = Awakenings(config["wakeup"], path)

    session_setup(app, SimpleCookieStorage())
    app.middlewares.append(aiohttp_session_flash.middleware)

    template_dir = op.join(path, "templates")
    aiohttp_jinja2.setup(
        app,
        loader=FileSystemLoader(template_dir),
        context_processors=(
            aiohttp_session_flash.context_processor,
        )
    )
    jinja2_env = aiohttp_jinja2.get_env(app)
    jinja2_env.globals['_'] = _

    app.router.add_get("/recording/cancel/{id:\d+}/", cancel_recording,
                       name="cancel_recording")
    app.router.add_get("/wakeup/cancel/{id:\d+}/", cancel_awakening,
                       name="cancel_awakening")

    app.router.add_routes(routes)
    static_dir = op.join(op.dirname(op.abspath(__file__)), "static")
    app.router.add_static("/static", static_dir)

    app.on_startup.append(startup)
    app.on_cleanup.append(cleanup)

    web.run_app(app, port=int(config["network"]["port"]))
