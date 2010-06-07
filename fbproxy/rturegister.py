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

""" Module enabling registration for realtime updates.

The most commonly used method is register, which takes the endpoint URL
and the app object, and registers for realtime updates if either the app's
cred or secret is available and valid.
"""
import httplib
import urllib
import random


randtoken = 0


def register_with_secret(appid, secret, fields, callback, server):
    """ Register the given application for realtime updates.

    Creates a subscription for user fields for the given application
    at the specified callback URL. This method takes the application secret
    as the second argument. Only one of register_with_secret and
    register_with_token needs to be called. In most cases, this should be
    taken care of by register().
    """
    token = appid + '|' + secret
    return register_with_token(appid, token, fields, callback, server)


def register_with_token(appid, token, fields, callback, server):
    """ Register the given application for realtime updates.

    Creates a subscription for user fields for the given application
    at the specified callback URL. This method takes an application's client
    credential access token as the second argument. Only one of
    register_with_secret and register_with_token needs to be called. In most
    cases, this should be taken care of by register().
    """
    fieldstr = ",".join(fields)
    headers = {'Content-type': 'applocation/x-www-form-urlencoded'}
    # use a random number as our verification token
    global randtoken
    if not randtoken:
        randtoken = random.randint(1, 1000000000)

    # make a POST to the graph API to register the endpoint
    postfields = {'object': 'user',
                  'fields': fieldstr,
                  'callback_url': callback,
                  'verify_token': randtoken}
    conn = httplib.HTTPSConnection(server)
    conn.request('POST', appid + '/subscriptions?access_token=' + token,
            urllib.urlencode(postfields), headers)
    response = conn.getresponse()
    if response.status == 200:
        return True
    else:
        print 'Error subscribing: graph server\'s response follows'
        print str(response.status) + " " + response.reason
        data = response.read()
        print data
        return False


def register(app, callback, server):
    """ Registers the given App, if possible.

    For registration to be possible, at least one of app.cred or app.secret
    must be defined.
    """
    subscribefields = app.good_fields | app.good_conns
    if app.cred:
        register_with_token(app.id, app.cred, subscribefields, callback, server)
    elif app.secret:
        register_with_secret(app.id, app.secret, subscribefields, callback,
                             server)
