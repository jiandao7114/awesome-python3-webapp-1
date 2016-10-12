import logging
import json
from aiohttp import web
from urllib import parse
from handlers import cookie2user, COOKIE_NAME
from model import User

# 在每个响应之前打印日志
async def logger_factory(app, handler):
    async def logger(request):
        logging.info('Request: %s %s' % (request.method, request.path))
        return await handler(request)
    return logger


# 通过cookie找到当前用户信息，把用户绑定在request.__user__
async def auth_factory(app, handler):
    async def auth(request):
        logging.info('check user: %s %s' % (request.method, request.path))
        cookie = request.cookies.get(COOKIE_NAME)
        request.__user__ = await cookie2user(cookie)
        if request.__user__ is not None:
            logging.info('set current user: %s' % request.__user__.email)
        return await handler(request)
    return auth


# async def auth_factory(app, handler):
#     async def auth(request):
#         logging.info('check user: %s %s' % (request.method, request.path))
#         request.__user__ = None
#         cookie_str = request.cookies.get(COOKIE_NAME)
#         if cookie_str:
#             user = await cookie2user(cookie_str)
#             if user:
#                 logging.info('set current user: %s' % user.email)
#                 request.__user__ = user
#         if request.path.startswith('/manage/') and (request.__user__ is None or not request.__user__.admin):
#             return web.HTTPFound('/signin')
#         return await handler(request)
#     return auth


async def data_factory(app, handler):
    async def parse_data(request):
        logging.info('data_factory...')
        # 处理POST请求
        if request.method == 'POST':
            # 判断content_type类型，例：‘Content-Type: text/html’
            if not request.content_type:
                return web.HTTPBadRequest(text='Missing Content_type.')
            content_type = request.content_type.lower()
            # 判断content_type类型是否为JSON数据格式，如果是，需先进行JSON数据交换处理
            # JSON(JavaScript Object Notation)为JavaScript原生格式，可以在其中被直接使用
            if content_type.startswith('application/json'):
                request.__data__ = await request.json()
                if not isinstance(request.__data__, dict):
                    return web.HTTPBadRequest(text='JSON body must be object.')
                logging.info('request json: %s' % request.__data__)
            elif content_type.startswith('application/x-www-form-urlencoded',
                                         'multipart/form-data'):
                params = await request.post()
                request.__data__ = dict(**params)
                logging.info('request form: %s' % request.__data__)
            else:
                return web.HTTPBadRequest(text='Unsupported Content-Type: %s' % content_type)
        # 处理GET请求
        elif request.method == 'GET':
            qs = request.query_string
            request.__data__ = {k: v[0] for k, v in parse.parse_qs(qs, True).items()}
            logging.info('request query: %s' % request.__data__)
        else:
            request.__data__ = dict()
        return await handler(request)
    return parse_data

# 将后端的返回值封装成浏览器可正确现实的Response对象
async def response_factory(app, handler):
    async def response(request):
        logging.info('Response handler...')
        r = await handler(request)
        if isinstance(r, web.StreamResponse):
            return r
        if isinstance(r, bytes):
            resp = web.Response(body=r)
            resp.content_type = 'application/octet-stream'
            return resp
        if isinstance(r, str):
            if r.startswith('redirect:'):
                return web.HTTPFound(r[9:])
            resp = web.Response(body=r.encode('utf-8'))
            resp.content_type = 'text/html;charset=utf-8'
            return resp
        if isinstance(r, dict):
            template = r.get('__template__')

            if template is None:
                resp = web.Response(body=json.dumps(r, ensure_ascii=False,
                                                    default=lambda o:
                                                    o.__dict__).encode('utf-8'))
                resp.content_type = 'application/json;charset=utf-8'
                return resp
            else:
                # 如果用jinja2渲染，绑定已验证过的用户
                r['__user__'] = request.__user__
                resp = web.Response(body=app['__templating__'].get_template(
                    template).render(**r).encode('utf-8'))
                resp.content_type = 'text/html;charset=utf-8'
                return resp
        if isinstance(r, int) and 100 <= r < 600:
            return web.Response(status=r)
        if isinstance(r, tuple) and len(r) == 2:
            status, message = r
            if isinstance(status, int) and 100<= status <600:
                # status为状态码，str(message)为附加信息
                return web.Response(status=status, text=str(message))

        # default
        resp = web.Response(body=str(r).encode('utf-8'))
        resp.content_type = 'text/html;charset=utf-8'
        return resp
    return response
