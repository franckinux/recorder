# from aiohttp_babel.middlewares import _
from aiohttp_session import get_session
# from babel.support import LazyProxy


def remove_special_data(dico):
    # del dico["csrf_token"]
    del dico["submit"]
    return dico


# async def generate_csrf_meta(request):
#     return {
#         "csrf_context": await get_session(request),
#         "csrf_secret": request.app["config"]["application"]["secret_key"].encode("ascii")
#     }


# def lazy_gettext(s):
#     return LazyProxy(_, s, enable_cache=False)
#
#
# _l = lazy_gettext
