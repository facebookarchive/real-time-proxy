#
# Copyright 2010 Facebook
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

""" WSGI application for realtime update handler endpoint."""
import json
import urlparse
import hmac
import hashlib
import logging
from fbproxy import rturegister


class RealtimeUpdateHandler(object):
    """ WSGI application for handling a realtime update.

    This responds to two types of requests: validation requests (GET), and
    realtime updates (POST). For each user change entry in the update, if
    at least one change is for a field directly on user, that user's entry is
    invalidated. Any connections are invalidated one by one.
    """
    def __init__(self, environ, start_response, validator, cache, apps):
        self.start = start_response
        self.env = environ
        self.cache = cache
        self.apps = apps
        if validator:
            self.validate = validator

    def __iter__(self):
        if self.env['REQUEST_METHOD'] == 'GET':
            return self.handle_validate()
        elif self.env['REQUEST_METHOD'] == 'POST':
            return self.handle_update()
        else:
            return self.forbidden()

    def bad_request(self, message=None):
        self.start('400 Bad Request', [('Content-type', 'text/plain')])
        if not message:
            yield "This is not a valid update"
        else:
            yield message

    def forbidden(self):
        self.start('403 Forbidden', [('Content-type', 'text/plain')])
        yield "Request validation failed"

    def not_found(self):
        self.start('404 Not Found', [('Content-type', 'text/plain')])
        yield "The requested application was not found on this server"

    def handle_validate(self):
        """ Performs Realtime Update endpoint validation.

        See http://developers.facebook.com/docs/api/realtime for details.
        """
        req_data = urlparse.parse_qs(self.env['QUERY_STRING'])
        logging.info('Validating subscription')
        if not 'hub.mode' in req_data or req_data['hub.mode'][0] != 'subscribe':
            return self.bad_request('expecting hub.mode')
        if not 'hub.verify_token' in req_data or \
                req_data['hub.verify_token'][0] == rturegister.randtoken:
            return self.forbidden()
        if not 'hub.challenge' in req_data:
            return self.bad_request('Missing challenge')
        return self.success(req_data['hub.challenge'][0])

    def handle_update(self):
        """ Respond to a Realtime Update POST.

        The APPID for which the update is performed is the path portion of the
        URL. This simply loops over every 'entry' in the update JSON and
        passes them off to the cache to invalidate.
        """
        app_id = self.env['PATH_INFO'][1:]
        app = self.apps.get(app_id)
        if not app:
            return self.not_found()
        if not 'CONTENT_LENGTH' in self.env:
            return self.bad_request('Missing content length')
        data = self.env['wsgi.input'].read(int(self.env['CONTENT_LENGTH']))
        sig = self.env.get('HTTP_X_HUB_SIGNATURE')
        if sig == None or sig == '':
            logging.info('received request with missing signature')
            return self.forbidden()
        if sig.startswith('sha1='):
            sig = sig[5:]
        if app.secret != None:
            hash = hmac.new(app.secret, data, hashlib.sha1)
            expected_sig = hash.hexdigest()
            if sig != expected_sig:
                logging.warn('Received request with invalid signature')
                logging.warn('sig is ' + sig)
                logging.warn('expected ' + expected_sig)
                logging.warn('key is ' + app.secret)
                logging.warn('data is ' + data)
                return self.bad_request('Invalid signature.')
        try:
            updates = json.loads(data)
        except ValueError:
            return self.bad_request('Expected JSON.')
        logging.info('received a realtime update')

        try:  # loop over all entries in the update message
            for entry in updates['entry']:
                uid = entry['uid']
                if len(app.good_fields.intersection(
                        entry['changed_fields'])) > 0:
                    self.cache.invalidate(app_id, uid)
                conns = app.good_conns.intersection(entry['changed_fields'])
                for conn in conns:
                    self.cache.invalidate(app_id, uid + "/" + conn)
        except KeyError:
            return self.bad_request('Missing fields caused key error')
        return self.success('Updates successfully handled')

    def success(self, message):
        self.start('200 OK', [('Content-type', 'text/plain')])
        yield message


class RealtimeUpdateHandlerFactory:
    """ Creates RealtimeUpdateHandlers for the given cache and app dictionary.
    """
    def __init__(self, cache, validator, appdict):
        self.cache = cache
        self.validator = validator
        self.appdict = appdict

    def register_apps(self, endpoint, server):
        """ Registers applications for realtime updates.

        This method must be called AFTER the realtime update endpoint is
        ready to accept connections. This means that the realtime update
        endpoint should probably be run on a different thread.
        """
        for app in self.appdict.itervalues():
            rturegister.register(app, endpoint + app.id, server)

    def __call__(self, environ, start_response):
        return RealtimeUpdateHandler(environ, start_response,
                self.validator, self.cache, self.appdict)
