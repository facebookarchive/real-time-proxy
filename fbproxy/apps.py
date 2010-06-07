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

""" A container for app-specific data and functionality."""
import threading
import logging


class App(object):
    """ Manages Facebook Application-specific settings and policies

    This class serves two purposes. First, it serves as a repository of
    information about an application (such as the users we have seen for it
    and the configuration settings for it). Second, it exposes two methods
    which are used in making cache-eligibilty decisions in ProxyRequestHandler,
     check_user and check_request. check_user adds the requestor to the app's
    list of seen users, and then sees if the user whose data we're requesting
    has been seen before (only users who we are sure have added an app will be
    updated by realtime updates, so we only cache requests for those users'
    data. check_request ensures that the request is only for data which is
    part of the app's realtime update subscription, and is not blacklisted.
    """

    def __init__(self, config):
        self.id = config['app_id']
        self.bad_fields = set()
        self.bad_conns = set()
        self.good_fields = set()
        self.good_conns = set()
        self.users = set()
        self.lock = threading.Lock()
        self.cred = config.get('app_cred')
        self.secret = config.get('app_secret')
        if 'blacklist_fields' in config:
            self.bad_fields.update(config['blacklist_fields'])
        if 'blacklist_connections' in config:
            self.bad_conns.update(config['blacklist_connections'])
        if 'whitelist_fields' in config:
            self.good_fields = set(config['whitelist_fields'])
        if 'whitelist_connections' in config:
            self.good_conns = set(config['whitelist_connections'])
        self.good_fields -= self.bad_fields
        self.good_conns -= self.bad_conns

    def check_user(self, requestor, requestee, default=None):
        """ Check a request's users.

        Adds the requestor to the known users for the app, and checks
        if the requestee is a known user of the app. Also adds the user
        to the default app, since we'll get updates for them.
        """
        self.lock.acquire()
        self.users.add(requestor)
        ok = requestee in self.users
        self.lock.release()

        # if this isn't the default app, also add the user to the default app
        if default != self and default != None:
            default.check_user(requestor, requestee)

        return ok

    def check_request(self, pathparts, fields=None):
        """ Returns whether a request is cacheable."""
        if not fields:
            fields = []
        if len(pathparts) == 1:  # this is a request for direct profile fields
            if len(set(fields) - self.good_fields) == 0:
                return True
            logging.info('got fields ' + repr(fields) + ' but only '
                         + repr(self.good_fields) + ' is ok')
        elif len(pathparts) == 2:  # this is a request for a connection
            return pathparts[1] in self.good_conns
        return False  # safety: if we're not certain about it, fall back to
                      # passthrough behavior


def init(configapps):
    """ Initializes the mapping of app ids to the App objects from config"""
    apps = dict((str(x['app_id']), App(x)) for x in configapps)
    if 'default' not in apps:  # Add the default app if settings haven't been
                               # defined for it already.
        default_app = App({'app_id': 'default'})
        intersect = lambda x, y: x & y
        default_app.good_fields = reduce(intersect, [x.good_fields for x
                                                     in apps.itervalues()])
        default_app.good_conns = reduce(intersect, [x.good_conns for x in
                                                    apps.itervalues()])
        apps['default'] = default_app
    return apps


def get_app(app_id, app_set):
    """Look up the given app in the app_set, using the default if needed."""
    if app_id in app_set:
        return app_set[app_id]
    if 'default' in app_set:
        return app_set['default']
    return None
