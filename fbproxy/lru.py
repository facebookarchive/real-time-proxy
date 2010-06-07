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

""" This module contains a simple LRU cache."""


class Node(object):
    """ An LRU node storing a key-value pair."""
    def __init__(self, key, value):
        self.key = key
        self.value = value
        self.prev = None
        self.successor = None

    def remove(self):
        """ Remove this node from the linked list."""
        if self.prev:
            self.prev.successor = self.successor
        if self.successor:
            self.successor.prev = self.prev
        self.prev = None
        self.successor = None

    def setnext(self, next):
        """ Move this node in the linked list (or insert it."""
        self.successor = next
        if next:
            self.prev = next.prev
            next.prev = self
            if self.prev:
                self.prev.successor = self
        else:
            self.prev = None

    def __repr__(self):
        return "(" + repr(self.key) + "," + repr(self.value) + ")"


class LRU(object):
    """ A simple Least-recently-used cache.

    This LRU cache functions by containing a linked list of nodes holding
    key-value pairs, and a dictionary index into this linked list. Changes
    to the size field will get reflected the next time the list's size
    changes (whether by a new insert or a deletion).
    """
    def __init__(self, size=10000):
        self.count = 0
        self.size = size
        self.head = None
        self.tail = None
        self.index = {}

    def __getitem__(self, key):
        """ fetch an item from the list, and update it's access time."""
        if key in self.index:
            node = self.index[key]
            node.remove()
            node.setnext(self.head)
            return self.index[key].value
        return None

    def __setitem__(self, key, value):
        """ update a value or insert a new value. Also checks for fullness."""
        node = None
        if key in self.index:
            node = self.index[key]
            node.remove()
            node.setnext(self.head)
            self.head = node
            node.value = value
        else:
            node = Node(key, value)
            self.index[key] = node
            if not self.head:
                self.tail = node
            node.setnext(self.head)
            self.head = node
            self.count += 1
        self.checksize()

    def __contains__(self, key):
        """ existence check. This does NOT update the access time."""
        return key in self.index

    def __delitem__(self, key):
        """ remove the item from the cache. does nothing if it not found."""
        if key in self.index:
            node = self.index[key]
            if node == self.tail:
                self.tail = node.prev
            if node == self.head:
                self.head = node.successor
            del self.index[key]
            self.count -= 1
            node.remove()
        self.checksize()

    def checksize(self):
        """ Prunes the LRU down to 'count' entries."""
        print "checksize called. Current count is " + str(self.count) + " of " \
                + str(self.size)
        while self.count > self.size:
            node = self.tail
            del self.index[node.key]
            self.tail = node.prev
            node.remove()
            self.count -= 1
