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

""" This module simply contains the ProxyLruCache class."""
import urllib
import json
import threading
import logging
from fbproxy.lru import LRU
from fbproxy.requesthandler import ProxyRequestHandler
from fbproxy.hashdict import HashedDictionary


SCALAR_TABLE = 1
VECTOR_TABLE = 2


class ProxyLruCache(object):
    """Implement a cache for Facebook Graph API Requests.

    This cache stores entries in a multi-tiered fashion. First requests are
    indexed by the app and path (aka the part of the URL before the ?). At most
    'size' such entries are maintained in an LRU cache. Underneath this, up to
    `width` views of this URL are stored (again in an LRU). Finally, underneath
    this is a mapping from access-token-less query strings to results.

    This implementation can be replaced. The relevant functions to implement
    are handle_request and invalidate.
    """
    def __init__(self, size):
        self.cache = LRU(size)
        self.lock = threading.Lock()

    def handle_request(self, query, path, querystring, app, server):
        """ handle a cacheable request. returns (status, headers, data) tuple.

        If it is found in the cache, just return the result directly from the
        cache. Otherwise make a request to the graph api server and return the
        result. If it is a 200 OK response, it gets saved in the cache, also.
        """
        accesstoken_parts = None
        accesstoken = None
        if 'access_token' in query:
            accesstoken = query['access_token'][0]
            accesstoken_parts = ProxyRequestHandler.parse_access_token(
                    query['access_token'][0])
            del query['access_token']
        appid = accesstoken_parts[0] if accesstoken_parts else '0'
        uid = accesstoken_parts[2] if accesstoken_parts else '0'

        usetable = '/' not in path  # use table for user directly
        # usetable = False
        fields = None
        if 'fields' in query and usetable:
            fields = query['fields'][0]
            del query['fields']

        key = path + "__" + appid
        subkey = uid + "__" + urllib.urlencode(query)
        value = None
        hashdict = None
        logging.debug('cache handling request with key ' + key +
                      ', and subkey ' + subkey + ' for user ' + uid)

        self.lock.acquire()
        if key in self.cache:
            # step 1. acquire the dictionary
            hashdict = self.cache[key]
            if subkey in hashdict:  # step 2: grab the relevant data if there
                value = hashdict[subkey]
        else:
            hashdict = HashedDictionary()
            self.cache[key] = hashdict
        self.lock.release()

        if value:  # step 3: return the data if available
            if usetable:
                (statusline, headers, table) = value
                return (statusline, headers, get_response(table, fields))
            else:
                return value

        # at this point, we have a cache miss
        # step 4: fetch data
        if usetable:
            (statusline, headers, table, status) = _fetchtable(query,
                    path, accesstoken, app, hashdict, subkey, server)
            # step 4.5: form a response body from the table
            if status != 200:
                # fetchtable returns body instead of table on error
                body = table
            else:
                for header in headers:
                    if header[0].upper() == 'CONTENT-LENGTH':
                        headers.remove(header)
                        break
                body = get_response(table, fields)
        else:
            (statusline, headers, body, status) = fetch_tuple(path,
                    querystring, server)
            if status == 200:
                hashdict[subkey] = ((statusline, headers, body), body)
        return (statusline, headers, body)

    def invalidate(self, appid, url):
        """ Invalidate a URL in an application's context.

        This removes all cache entries for the given applicaton and path.
        """
        key = url + "__" + appid
        logging.debug('invalidating' + key)
        self.lock.acquire()
        if key in self.cache:
            del self.cache[key]
        # also invalidate the URL for the null app
        key = url + "__0"
        if key in self.cache:
            del self.cache[key]
        self.lock.release()


def _response_to_table(body):
    """ Takes a JSON response body and converts into a key-value store."""
    table = {}
    try:
        bodyjson = json.loads(body)
        for (key, value) in bodyjson.iteritems():
            table[key] = value
    except ValueError:
        pass
    return table


def get_response(table, fields):
    """ Fetches the given fields from the table and returns it as JSON."""
    ret = {}
    if fields:
        fieldlist = fields.split(',')
        for field in fieldlist:
            if field in table:
                ret[field] = table[field]
    else:
        for key, value in table.iteritems():
            if key[0] != '_':
                ret[key] = value

    return json.dumps(ret)


def _fetchtable(query, path, accesstoken, app, hashdict, key, server):
    """ Fetches the requested object, returning it as a field-value table.

    In addition, it will make use of the hash dict to avoid parsing the
    body if possible (and store the response there as appropriate.
    """
    fields = ','.join(app.good_fields)
    query['fields'] = fields
    query['access_token'] = accesstoken
    (statusline, headers, data, statuscode) = fetch_tuple(path, \
            urllib.urlencode(query), server)
    # error = send the raw response instead of a table
    if statuscode != 200:
        return (statusline, headers, data, statuscode)
    # hash miss = have to parse the file
    elif not hashdict.contains_hash(data):
        hashdict[key] = ((statusline, headers, _response_to_table(data)), data)
    else:  # statuscode == 200 and hashdict has the hash of the data
        hashdict[key] = (None, data)  # the stored data arg is ignored
                                      # since the hash is in the dict
    (statusline, headers, table) = hashdict[key]
    return (statusline, headers, table, 200)


def fetch_tuple(path, querystring, server):
    """ Fetches the requested object as (status, headers, body, status num)"""
    response = ProxyRequestHandler.fetchurl('GET', path, querystring, server)
    statusline = str(response.status) + " " + response.reason
    headers = response.getheaders()
    body = response.read()
    response.close()
    return (statusline, headers, body, response.status)
