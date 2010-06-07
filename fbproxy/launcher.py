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

""" main driver for the Facebook Graph API Proxy with Real-time Update support

All configuration is done by editing config.py. This file simply launches two
web servers. one for the realtime update endpoint, and one for the proxy
itself. The realtime endpoint needs to be accessible publically, while the
proxy endpoint should be accessible only from a small set of machines
(ideally the web servers that would otherwise be making direct Facebook Graph
API calls).
"""
import threading
import time
from cherrypy import wsgiserver
from fbproxy import config, apps
from fbproxy.requesthandler import ProxyRequestHandlerFactory
from fbproxy.cache import ProxyLruCache
from fbproxy.rtendpoint import RealtimeUpdateHandlerFactory


GRAPH_SERVER = "graph.facebook.com"


def launch(config_file):
    """ Launch the Graph Proxy with the specified config_file."""
    config.load(config_file)
    cache = ProxyLruCache(config.cache_entries)
    appdict = apps.init(config.apps)

    request_handler_factory = ProxyRequestHandlerFactory(None,
            cache, appdict, GRAPH_SERVER)
    realtime_handler_factory = RealtimeUpdateHandlerFactory(cache, None,
                                                            appdict)
    endpoint = "http://" + config.public_hostname + ":" + str(
            config.realtime_port) + "/"

    proxyserver = wsgiserver.CherryPyWSGIServer((config.proxy_interface,
        config.proxy_port), request_handler_factory)
    rtuserver = wsgiserver.CherryPyWSGIServer((config.realtime_interface,
        config.realtime_port), realtime_handler_factory)

    realtime_port_thread = threading.Thread(target=rtuserver.start)
    realtime_port_thread.daemon = True
    realtime_port_thread.start()
    time.sleep(2)  # give the server time to come up

    realtime_handler_factory.register_apps(endpoint, GRAPH_SERVER)

    try:
        proxyserver.start()
    except KeyboardInterrupt:
        proxyserver.stop()
        rtuserver.stop()
