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

""" This module contains the HashedDictionary class.

This is a smart dictionary which stores values that have identical hashes only
once, to save space.
"""

import hashlib


class HashedDictionary(object):
    """ A smarter dictionary. Stores responses with identical body only once.

    This dictionary stores (nonhashed_data, hashed_data) tuples, hashing by
    body. The goal is to only store responses which are identical once. We
    do this by mapping from the key to a hash of the response. From there,
    we access the actual response in a second dictionary. Note that parts
    of requests are significant, while others are not. Consumers are expected
    to partition their data into nonhashed and hashed data for insertion and
    retrieval.
    """
    def __init__(self):
        self.content = {}
        self.keymap = {}

    def __getitem__(self, key):
        """ Fetch the tuple for the given key."""
        if key in self.keymap:
            valhash = self.keymap[key]
            return self.content[valhash]
        return None

    def __setitem__(self, key, data):
        """ Store the given response in the dictionary with the given key.

        Takes values as (data, hashed_data). hashes hash_data, and then stores
        data if that hash is unique. If that hash is not unique, then this will
        point key at the existing entry with that hash.
        """
        (stored_data, valhashed) = data
        valhash = hashlib.sha1(valhashed).digest()
        self.keymap[key] = valhash
        if not valhash in self.content:
            self.content[valhash] = stored_data

    def __contains__(self, key):
        return key in self.keymap

    def contains_hash(self, valhashdata):
        """ Determines if the data has a matching hash already in the dict."""
        return hashlib.sha1(valhashdata).digest() in self.content
