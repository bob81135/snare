import logging
import aiohttp
from aiohttp import web
from aiohttp.web import StaticResource as StaticRoute
import aiohttp_jinja2
import jinja2
import json
from snare.middlewares import SnareMiddleware
from snare.tanner_handler import TannerHandler
from aiohttp.abc import AbstractAccessLogger
from http_basic_auth import parse_header
import os
from snare.utils.get_setting_file import get_setting
setting_dir = ""
class RuleAccessLogger(AbstractAccessLogger):
    def log_message(self, remote, port, log_type, raw_data):
        log_string = [remote, port, log_type, raw_data]
        self.logger.info(json.dumps(log_string))
    def log(self, request, response, time):
        global setting_dir
        setting_info = get_setting(setting_dir)
        port = request.host.split(":")[-1]
        if(response.status in [401,403]):
            try:
                login, password = parse_header(request.headers["Authorization"])
                user = {}
                user[login] = password
                # print("暴力破解",request.path_qs, login, password)
                self.log_message(request.remote, port, "loginFaild", json.dumps(user))
            except:
                pass
        elif(response.status==404):
            filename, file_extension = os.path.splitext(request.path_qs)
            if(file_extension==""):
                # print("目錄猜測",request.path_qs)
                self.log_message(request.remote, port, "directoryGuess", request.path_qs)
            else:
                # print("檔案猜測",request.path_qs)
                self.log_message(request.remote, port, "fileGuess", request.path_qs)
        elif(response.status==200):
            if("Authorization" in request.headers and self.check_list(request.path_qs,setting_info['auth_list'])):
                try:
                    login, password = parse_header(request.headers["Authorization"])
                    user = {}
                    user[login] = password
                    # print("登入成功",request.path_qs, login,password)
                    self.log_message(request.remote, port, "loginSuccess", json.dumps(user))
                except:
                    pass
            if(self.check_list(request.path_qs, setting_info['sensitives'])):
                # print("敏感資料",request.path_qs)
                self.log_message(request.remote, port, "sensitiveFiles", request.path_qs)
    def check_list(self, url, path_list):
        filename, file_extension = os.path.splitext(url)
        for path in path_list:
            pathname, path_extension = os.path.splitext(path)
            if(file_extension==""):
                filename+="/"
            if(path_extension==""):
                pathname+="/"
                if(filename.startswith(pathname)):
                    return True
            else:
                if(url == path):
                    return True
        return False
class HttpRequestHandler():
    def __init__(
            self,
            meta,
            run_args,
            snare_uuid,
            debug=False,
            keep_alive=75,
            **kwargs):
        self.run_args = run_args
        self.dir = run_args.full_page_path
        global setting_dir 
        setting_dir = self.dir
        self.setting_info = get_setting(setting_dir)
        self.meta = meta
        self.snare_uuid = snare_uuid
        self.logger = logging.getLogger(__name__)
        self.sroute = StaticRoute(
            name=None, prefix='/',
            directory=self.dir
        )
        self.tanner_handler = TannerHandler(run_args, meta, snare_uuid)

    async def submit_slurp(self, data):
        try:
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(verify_ssl=False)) as session:
                r = await session.post(
                    'https://{0}:8080/api?auth={1}&chan=snare_test&msg={2}'.format(
                        self.run_args.slurp_host, self.run_args.slurp_auth, data
                    ), json=data, timeout=10.0
                )
                assert r.status == 200
                r.close()
        except Exception as e:
            self.logger.error('Error submitting slurp: %s', e)

    async def handle_request(self, request):
        # self.logger.info('Request path: {0}'.format(request.path_qs))
        data = self.tanner_handler.create_data(request, 200)
        if request.method == 'POST':
            post_data = await request.post()
            # self.logger.info('POST data:')
            # for key, val in post_data.items():
            #     self.logger.info('\t- {0}: {1}'.format(key, val))
            data['post_data'] = dict(post_data)

        # Submit the event to the TANNER service
        event_result = await self.tanner_handler.submit_data(data)

        # Log the event to slurp service if enabled
        if self.run_args.slurp_enabled:
            await self.submit_slurp(request.path_qs)

        content, headers, status_code = await self.tanner_handler.parse_tanner_response(
            request.path_qs, event_result['response']['message']['detection'])

        if self.run_args.server_header:
            headers['Server'] = self.run_args.server_header

        if 'cookies' in data and 'sess_uuid' in data['cookies']:
            previous_sess_uuid = data['cookies']['sess_uuid']
        else:
            previous_sess_uuid = None

        if event_result is not None and\
                'sess_uuid' in event_result['response']['message']:
            cur_sess_id = event_result['response']['message']['sess_uuid']
            if previous_sess_uuid is None or not previous_sess_uuid.strip() or previous_sess_uuid != cur_sess_id:
                headers.add('Set-Cookie', 'sess_uuid=' + cur_sess_id)

        return web.Response(body=content, status=status_code, headers=headers)

    async def start(self):
        app = web.Application()
        app.add_routes([web.route('*', '/{tail:.*}', self.handle_request)])
        aiohttp_jinja2.setup(
            app, loader=jinja2.FileSystemLoader(self.dir)
        )
        middleware = SnareMiddleware(
            error_404=self.meta['/status_404'].get('hash'),
            headers=self.meta['/status_404'].get('headers', []),
            server_header=self.run_args.server_header
        )
        middleware.setup_middlewares(app)
        middleware.auth_middlewares(app, self.setting_info['auth_list'], self.setting_info['user_dict'])
        
        self.runner = web.AppRunner(app,access_log_class=RuleAccessLogger)
        await self.runner.setup()
        site = web.TCPSite(
            self.runner,
            self.run_args.host_ip,
            self.run_args.port)

        await site.start()
        names = sorted(str(s.name) for s in self.runner.sites)
        print("======== Running on {} ========\n"
              "(Press CTRL+C to quit)".format(', '.join(names)))

    async def stop(self):
        await self.runner.cleanup()
