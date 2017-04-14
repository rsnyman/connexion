import logging
import falcon
import pathlib
from types import FunctionType  # NOQA

import werkzeug.exceptions

from ..apis.falcon_api import FalconApi
from ..exceptions import ProblemException
from ..problem import problem
from .abstract import AbstractApp

logger = logging.getLogger('connexion.app')


class FalconApp(AbstractApp):
    def __init__(self, import_name, **kwargs):
        super(FalconApp, self).__init__(import_name, FalconApi, server='gevent', **kwargs)

    def create_app(self):
        app = falcon.API()
        return app

    def get_root_path(self):
        # TODO
        return pathlib.Path('/')

    def set_errors_handlers(self):
        for error_code in werkzeug.exceptions.default_exceptions:
            self.add_error_handler(error_code, self.common_error_handler)

        self.add_error_handler(ProblemException, self.common_error_handler)

    @staticmethod
    def common_error_handler(exception):
        """
        :type exception: Exception
        """
        if isinstance(exception, ProblemException):
            response = exception.to_problem()
        else:
            if not isinstance(exception, werkzeug.exceptions.HTTPException):
                exception = werkzeug.exceptions.InternalServerError()

            response = problem(title=exception.name, detail=exception.description,
                               status=exception.code)

        return FalconApi.get_response(response)

    def add_api(self, specification, **kwargs):
        api = super(FalconApp, self).add_api(specification, **kwargs)
        api.add_routes(self.app)
        return api

    def add_error_handler(self, error_code, function):
        # type: (int, FunctionType) -> None
        # TODO
        pass

    def run(self, port=None, server=None, debug=None, host=None, **options):  # pragma: no cover
        """
        Runs the application on a local development server.
        :param host: the host interface to bind on.
        :type host: str
        :param port: port to listen to
        :type port: int
        :param server: which wsgi server to use
        :type server: str | None
        :param debug: include debugging information
        :type debug: bool
        :param options: options to be forwarded to the underlying server
        :type options: dict
        """
        # this functions is not covered in unit tests because we would effectively testing the mocks

        # overwrite constructor parameter
        if port is not None:
            self.port = port
        elif self.port is None:
            self.port = 5000

        self.host = host or self.host or '0.0.0.0'

        if server is not None:
            self.server = server

        if debug is not None:
            self.debug = debug

        logger.debug('Starting %s HTTP server..', self.server, extra=vars(self))
        if self.server == 'tornado':
            try:
                import tornado.wsgi
                import tornado.httpserver
                import tornado.ioloop
            except:
                raise Exception('tornado library not installed')
            wsgi_container = tornado.wsgi.WSGIContainer(self.app)
            http_server = tornado.httpserver.HTTPServer(wsgi_container, **options)
            http_server.listen(self.port, address=self.host)
            logger.info('Listening on %s:%s..', self.host, self.port)
            tornado.ioloop.IOLoop.instance().start()
        elif self.server == 'gevent':
            try:
                import gevent.wsgi
            except:
                raise Exception('gevent library not installed')
            http_server = gevent.wsgi.WSGIServer((self.host, self.port), self.app, **options)
            logger.info('Listening on %s:%s..', self.host, self.port)
            http_server.serve_forever()
        else:
            raise Exception('Server %s not recognized', self.server)
