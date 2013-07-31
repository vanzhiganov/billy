from __future__ import unicode_literals

from base64 import b64encode
import json

from flask import url_for, Response
from unittest import TestCase
from werkzeug.test import Client

from api.app import app
from settings import TEST_API_KEYS


class ClientResponse(Response):
    def json(self):
        if self.content_type != 'application/json':
            error = 'content_type is not application/json! Got {0} instead.'
            raise TypeError(error.format(self.content_type))
        return json.loads(self.data.decode('utf-8'))


class TestClient(Client):
    def _add_headers(self, user, kwargs):
        if user and user.api_key:
            kwargs.get('headers', {})['Authorization'] = \
                'Basic {}'.format(b64encode(':{}'.format(user.api_key)))
        return kwargs

    def get(self, url, user=None, *args, **kwargs):
        kwargs = self._add_headers(user, kwargs)
        return super(self.__class__, self).get(url, *args, **kwargs)

    def post(self, url, user=None, *args, **kwargs):
        kwargs = self._add_headers(user, kwargs)
        return super(self.__class__, self).post(url, *args, **kwargs)

    def put(self, url, user=None, *args, **kwargs):
        kwargs = self._add_headers(user, kwargs)
        return super(self.__class__, self).put(url, *args, **kwargs)

    def delete(self, url, user=None, *args, **kwargs):
        kwargs = self._add_headers(user, kwargs)
        return super(self.__class__, self).delete(url, *args, **kwargs)


class BaseTestCase(TestCase):
    def setUp(self):
        super(BaseTestCase, self).setUp()
        self.api_key = TEST_API_KEYS[0]
        self.auth_headers = {
            'Authorization': 'Basic {}'.format(b64encode(
                ':{}'.format(self.api_key)))
        }

        self.client = TestClient(app, response_wrapper=ClientResponse)
        self.test_users = [
            type(str('group_user_{}'.format(i)), (), {'api_key': value}) for
            i, value in enumerate(TEST_API_KEYS)]
        self.ctx = app.test_request_context()
        self.ctx.push()

    def url_for(self, *args, **kwargs):
        return url_for(*args, **kwargs)

    def check_error(self, resp, error_expected):
        self.assertEqual(resp.json, True)

    def check_schema(self, resp, schema):
        pass
