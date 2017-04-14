import json
import logging
import falcon.status_codes

import six
import werkzeug.exceptions

from connexion.apis.abstract import AbstractAPI
from connexion.decorators.produces import NoContent
from connexion.handlers import AuthErrorHandler
from connexion.lifecycle import ConnexionRequest, ConnexionResponse
from connexion.utils import is_json_mimetype

logger = logging.getLogger('connexion.apis.falcon_api')


class SwaggerJsonResource():

    def __init__(self, specification):
        self.body = json.dumps(specification)

    def on_get(self, req, resp):
        resp.body = self.body


class FalconApi(AbstractAPI):
    def _set_base_path(self, base_path):
        super(FalconApi, self)._set_base_path(base_path)
        self.routes = []

    def json_loads(self, data):
        """
        Use specific JSON loader
        """
        return Jsonifier.loads(data)

    def add_swagger_json(self):
        """
        Adds swagger json to {base_path}/swagger.json
        """
        logger.debug('Adding swagger.json: %s/swagger.json', self.base_path)
        self.routes.append(('/swagger.json', SwaggerJsonResource(self.specification)))

    def add_swagger_ui(self):
        """
        Adds swagger ui to {base_path}/ui/
        """
        console_ui_path = self.options.openapi_console_ui_path.strip('/')
        logger.debug('Adding swagger-ui: %s/%s/',
                     self.base_path,
                     console_ui_path)

        static_files_url = '/{console_ui_path}/<path:filename>'.format(
            console_ui_path=console_ui_path)

        #self.blueprint.add_url_rule(static_files_url,
        #                            static_endpoint_name,
        #                            self._handlers.console_ui_static_files)

        #index_endpoint_name = "{name}_swagger_ui_index".format(name=self.blueprint.name)
        #console_ui_url = '/{swagger_url}/'.format(
        #    swagger_url=self.options.openapi_console_ui_path.strip('/'))

        #self.blueprint.add_url_rule(console_ui_url,
        #                            index_endpoint_name,
        #                            self._handlers.console_ui_home)

    def add_auth_on_not_found(self, security, security_definitions):
        """
        Adds a 404 error handler to authenticate and only expose the 404 status if the security validation pass.
        """
        logger.debug('Adding path not found authentication')
        not_found_error = AuthErrorHandler(self, werkzeug.exceptions.NotFound(), security=security,
                                           security_definitions=security_definitions)
        #self.blueprint.add_url_rule('/<path:invalid_path>', endpoint_name, not_found_error.function)

    def _add_operation_internal(self, method, path, operation):
        operation_id = operation.operation_id
        logger.debug('... Adding %s -> %s', method.upper(), operation_id,
                     extra=vars(operation))

        function = operation.function
        resource = type('Resource', (object,), {'on_{}'.format(method): function})
        self.routes.append((self.base_path + path, resource()))

    def add_routes(self, falcon_api):
        # falcon_api is of type falcon.API()
        # see https://falcon.readthedocs.io/en/stable/api/api.html
        for uri_template, resource in self.routes:
            falcon_api.add_route(uri_template, resource)

    @property
    def _handlers(self):
        # type: () -> InternalHandlers
        if not hasattr(self, '_internal_handlers'):
            self._internal_handlers = InternalHandlers(self.base_path, self.options)
        return self._internal_handlers

    @classmethod
    def get_response(cls, response, mimetype=None, request=None):
        """Gets ConnexionResponse instance for the operation handler
        result. Status Code and Headers for response.  If only body
        data is returned by the endpoint function, then the status
        code will be set to 200 and no headers will be added.
        """
        logger.debug('Getting data and status code',
                     extra={
                         'data': response,
                         'data_type': type(response),
                         'url': 'TODO',
                     })

        falcon_response = request.context.falcon_response

        if response == falcon_response:
            pass
        elif isinstance(response, ConnexionResponse):
            falcon_response.status = cls._get_status(response.status_code)
            falcon_response.content_type = response.content_type or response.mimetype
            falcon_response.body = response.body
            falcon_response.set_headers(response.headers or {})
        else:
            cls._set_falcon_response(response, mimetype, falcon_response)

        logger.debug('Got data and status code (%s)',
                     falcon_response.status,
                     extra={
                         'data': response,
                         'datatype': type(response),
                         'url': 'TODO'
                     })

        return falcon_response

    @classmethod
    def _jsonify_data(cls, data, mimetype):
        if (isinstance(mimetype, six.string_types) and is_json_mimetype(mimetype)) \
                or not (isinstance(data, six.binary_type) or isinstance(data, six.text_type)):
            return Jsonifier.dumps(data)

        return data

    @staticmethod
    def _get_status(status_code):
        return getattr(falcon.status_codes, 'HTTP_{}'.format(status_code))

    @classmethod
    def _set_falcon_response(cls, response, mimetype, falcon_response):
        falcon_response.content_type = mimetype


        if isinstance(response, tuple) and len(response) == 3:
            data, status_code, headers = response
            falcon_response.status = cls._get_status(status_code)
            falcon_response.set_headers(headers or {})
        elif isinstance(response, tuple) and len(response) == 2:
            data, status_code = response
            falcon_response.status = cls._get_status(status_code)
        else:
            falcon_response.status = falcon.HTTP_200
            data = response

        if data is not None and data is not NoContent:
            data = cls._jsonify_data(data, mimetype)
            falcon_response.body = data
        elif data is NoContent:
            falcon_response.body = ''


    @classmethod
    def get_request(cls, resource, falcon_request, falcon_response, *args, **params):
        # type: (*Any, **Any) -> ConnexionRequest
        """Gets ConnexionRequest instance for the operation handler
        result. Status Code and Headers for response.  If only body
        data is returned by the endpoint function, then the status
        code will be set to 200 and no headers will be added.

        :rtype: ConnexionRequest
        """
        print(cls, args, params)
        request = ConnexionRequest(
            falcon_request.url,
            falcon_request.method,
            headers=falcon_request.headers,
            form={},
            query=falcon_request.params,
            body=None,
            json=None,
            files={},
            path_params=params,
            context=FalconRequestContextProxy(falcon_request, falcon_response)
        )
        logger.debug('Getting data and status code',
                     extra={
                         'data': request.body,
                         'data_type': type(request.body),
                         'url': request.url
                     })
        return request


class FalconRequestContextProxy(object):
    """"Proxy assignments from `ConnexionRequest.context`
    to `falcon.Request` instance.
    """

    def __init__(self, falcon_request, falcon_response):
        self.falcon_request = falcon_request
        self.falcon_response = falcon_response
        self.values = {}

    def __setitem__(self, key, value):
        # type: (str, Any) -> None
        logger.debug('Setting "%s" attribute in falcon_request', key)
        self.falcon_request.context[key] = value
        self.values[key] = value

    def items(self):
        # type: () -> list
        return self.values.items()


class Jsonifier(object):
    @staticmethod
    def dumps(data):
        """ Central point where JSON serialization happens inside
        Connexion.
        """
        return "{}\n".format(json.dumps(data, indent=2))

    @staticmethod
    def loads(data):
        """ Central point where JSON serialization happens inside
        Connexion.
        """
        if isinstance(data, six.binary_type):
            data = data.decode()

        try:
            return json.loads(data)
        except Exception as error:
            if isinstance(data, six.string_types):
                return data


class InternalHandlers(object):
    """
    Flask handlers for internally registered endpoints.
    """

    def __init__(self, base_path, options):
        self.base_path = base_path
        self.options = options

    def console_ui_home(self):
        """
        Home page of the OpenAPI Console UI.

        :return:
        """
        return flask.render_template('index.html', api_url=self.base_path)

    def console_ui_static_files(self, filename):
        """
        Servers the static files for the OpenAPI Console UI.

        :param filename: Requested file contents.
        :return:
        """
        # convert PosixPath to str
        static_dir = str(self.options.openapi_console_ui_from_dir)
        return flask.send_from_directory(static_dir, filename)
