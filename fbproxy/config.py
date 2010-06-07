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

""" Central configuration location for the proxy.

The load function must be called before attempting to use this module."""
import imp


def load(cfgfile):
    """ Loads the specified configuration into this module."""
    local_config = imp.load_source('local_config', cfgfile)
    mydict = globals()

    for key in local_config.__dict__:
        mydict[key] = local_config.__dict__[key]
