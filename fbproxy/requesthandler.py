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

""" WSGI application for the proxy endpoint."""
import httplib
import urlparse
import logging

USER_FIELDS = ['first_name', 'last_name', 'name', 'hometown', 'location',
               'about', 'bio', 'relationship_status', 'significant_other',
               'work', 'education', 'gender']
INVALIDATE_MAP = {'feed': ['statuses', 'feed', 'links'],
                  'links': ['feed', 'links']}


class ProxyRequestHandler(object):
    """ WSGI application for handling a graph API request

    This takes requests, and either passes them through to config.graph_server
    or fulfills them from a cache. There are multiple reasons that a request
    might not be eligible to be cached, though. Specifically, these are:

    1. The request contains a field which is not enabled for realtime updates.
    2. The request is not a GET request
    3. The application has not seen a request from the targeted user before
        (based on access_token). Note that this will never prevent caching
        of a request for information about the current user. (see App.check_user
        in AppStateHandler for details)
    4. The request fails the application's check_request() verification.
    5. The request is not for a user or a direct connection of user
    6. A validator is present and the request fails its validation

    For requests which are not GET requests, we also proactively invalidate
    cache entries which are likely to be affected by such requests. See
    ProxyLruCache for details about the caching strategy.
    """
    def __init__(self, environ, start_response, validator, cache, appdict,
                 server):
        self.start = start_response
        self.env = environ
        self.cache = cache
        self.apps = appdict
        self.server = server
        # the following fields will be set in __iter__
        self.uriparts = None
        self.acctoken_pieces = None
        self.query_parms = None
        if validator:
            self.validate = validator

    def __iter__(self):
        """ fulfills a graph API request."""
        # parse the request
        self.uriparts = self.env['PATH_INFO'].strip('/').split('/')
        self.query_parms = urlparse.parse_qs(self.env['QUERY_STRING'])
        app = None
        if hasattr(self, 'validate'):
            if not self.validate(self.env):
                return self.forbidden()
        # determine the viewer context and application, if access token exists
        if 'access_token' in self.query_parms:
            self.acctoken_pieces = self.parse_access_token(
                    self.query_parms['access_token'][0])
            if self.acctoken_pieces:
                app = self.apps[self.acctoken_pieces[0]] \
                        if self.acctoken_pieces[0] in self.apps \
                        else None
            else:
                app = self.apps['default'] if 'default' in self.apps \
                    else None
        else:
            self.acctoken_pieces = ['', '', '', '']

        self.fixurl()  # replace /me with the actual UID, to enable sane caching
        self.env['PATH_INFO'] = '/'.join(self.uriparts)

        # last chance to load an app to handle this
        if not app and 'default' in self.apps:
            app = self.apps['default']
        if not app:
            logging.info('bypassing cache due to missing application settings')
            return self.pass_through()  # app is missing from config, so don't
                                        # cache
        # non-GETs typically change the results of subsequent GETs. Thus we
        # invalidate opportunistically.
        if self.env['REQUEST_METHOD'] != 'GET':
            self.invalidate_for_post(app)
            return self.pass_through()
        fields = USER_FIELDS  # default fields if not specified
        if 'fields' in self.query_parms:
            fields = self.query_parms['fields'][0].split(',')
        if not app.check_user(self.acctoken_pieces[2], self.uriparts[0],
                              self.apps.get('default')):
            logging.info('bypassing cache since user not known to be app user')
            return self.pass_through()
        if self.cannotcache():
            logging.info('bypassing cache because the URI is not cacheable')
            return self.pass_through()
        if not app.check_request(self.uriparts, fields):
            logging.info('bypassing cache since the app rejected the request')
            return self.pass_through()

        if self.cache:
            return self.do_cache(app, self.server)
        else:
            logging.warning('cache does not exist. passing request through')
            return self.pass_through()

    @staticmethod
    def parse_access_token(acctok):
        """ Split up an access_token into 4 parts.

        This fails on non-user access tokens.
        """
        try:
            acctoken_firstsplit = acctok.split('-', 1)
            acctoken_all = acctoken_firstsplit[0].split('|')
            acctoken_all.extend(acctoken_firstsplit[1].split('|'))
            if len(acctoken_all) != 4:
                return False
            return acctoken_all
        except IndexError:
            return False

    @staticmethod
    def fetchurl(reqtype, path, querystring, server):
        """ fetch the requested object from the Facebook Graph API server."""
        conn = httplib.HTTPSConnection(server)
        conn.request(reqtype, path + "?" + querystring)
        response = conn.getresponse()
        return response

    # connections which are known not to work with the Graph API.
    # See http://developers.facebook.com/docs/api/realtime for details
    connections_blacklist = ['home', 'tagged', 'posts', 'likes', 'photos', \
            'albums', 'videos', 'groups', 'notes', 'events', 'inbox', 'outbox',
            'updates']

    def cannotcache(self):
        """ A set of simple rules for ruling out some requests from caching."""
        # rule 0: Only GET requests can be fetched.
        # All others are assumed to have side effects
        if self.env['REQUEST_METHOD'] != 'GET':
            return True

        # rule 1: Reject if the request is not realtime-enabled.
        #    Specifically, it must either be a request for an item directly, or
        #    for an object which is not a blacklisted connection of users
        if len(self.uriparts) > 2:
            return True
        if len(self.uriparts) == 2:
            if self.uriparts[1] in ProxyRequestHandler.connections_blacklist:
                return True
        return False

    def fixurl(self):
        """ Replace "me" with the user's actual UID."""
        if self.uriparts[0].upper() == "ME":
            if self.acctoken_pieces[2] != '':
                self.uriparts[0] = self.acctoken_pieces[2]

    def pass_through(self):
        """ Satisfy a request by just proxying it to the Graph API server."""
        response = self.fetchurl(self.env['REQUEST_METHOD'],
                self.env['PATH_INFO'], self.env['QUERY_STRING'], self.server)
        self.start(str(response.status) + " " +
                response.reason, response.getheaders())
        data = response.read()
        response.close()
        yield data

    def do_cache(self, app, server):
        """ Satisfy a request by passing it to the Cache."""
        cached_response = self.cache.handle_request(self.query_parms,
                self.env['PATH_INFO'], self.env['QUERY_STRING'], app, server)
        self.start(cached_response[0], cached_response[1])
        yield cached_response[2]

    def forbidden(self):
        self.start('403 Forbidden', [('Content-type', 'text/plain')])
        yield "Failed to validate request\n"

    def internal_error(self):
        self.start('500 Internal Server Error',
                [('Content-type', 'text/plain')])
        yield "An internal error occurred\n"

    def invalidate_for_post(self, app):
        """ Invalidates possibly affected URLs after a non-GET.

        The behavior of this is controlled by invalidate_map in config.py
        """
        if len(self.uriparts) != 2:
            return
        if not self.uriparts[1] in INVALIDATE_MAP:
            return
        for field in INVALIDATE_MAP[self.uriparts[1]]:
            logging.debug('invalidating ' + self.uriparts[0] + '/' + field)
            self.cache.invalidate(app.id, "/" + self.uriparts[0] + "/" + field)


class ProxyRequestHandlerFactory(object):
    """ factory for request handlers.

    This is called by WSGI for each request. Note that this and any code
    called by it can be running in multiple threads at once.
    """
    def __init__(self, validator, cache, apps, server):
        self.validator = validator
        self.cache = cache
        self.apps = apps
        self.server = server

    def __call__(self, environ, start_response):
        return ProxyRequestHandler(environ, start_response,
                self.validator, self.cache, self.apps, self.server)
