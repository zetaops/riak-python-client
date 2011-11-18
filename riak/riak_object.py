"""
Copyright 2010 Rusty Klophaus <rusty@basho.com>
Copyright 2010 Justin Sheehy <justin@basho.com>
Copyright 2009 Jay Baird <jay@mochimedia.com>

This file is provided to you under the Apache License,
Version 2.0 (the "License"); you may not use this file
except in compliance with the License.  You may obtain
a copy of the License at

  http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing,
software distributed under the License is distributed on an
"AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
KIND, either express or implied.  See the License for the
specific language governing permissions and limitations
under the License.
"""
import types, copy, re
from metadata import *
from riak import RiakError
from riak.riak_index_entry import RiakIndexEntry

class RiakObject(object):
    """
    The RiakObject holds meta information about a Riak object, plus the
    object's data.
    """
    def __init__(self, client, bucket, key=None):
        """
        Construct a new RiakObject.

        :param client: A RiakClient object.
        :type client: :class:`RiakClient <riak.client.RiakClient>`
        :param bucket: A RiakBucket object.
        :type bucket: :class:`RiakBucket <riak.bucket.RiakBucket>`
        :param key: An optional key. If not specified, then the key
         is generated by the server when :func:`store` is called.
        :type key: string
        """
        try:
            if isinstance(key, basestring):
                key = key.encode('ascii')
        except UnicodeError:
            raise TypeError('Unicode keys are not supported.')

        self._client = client
        self._bucket = bucket
        self._key = key
        self._encode_data = True
        self._vclock = None
        self._data = None
        self._metadata = {MD_USERMETA: {}, MD_INDEX: []}
        self._links = []
        self._siblings = []
        self._exists = False

    def get_bucket(self):
        """
        Get the bucket of this object.

        :rtype: RiakBucket
        """
        return self._bucket;

    def get_key(self):
        """
        Get the key of this object.

        :rtype: string
        """
        return self._key


    def get_data(self):
        """
        Get the data stored in this object. Will return an associative
        array, unless the object was constructed with
        :func:`RiakBucket.new_binary <riak.bucket.RiakBucket.new_binary>` or
        :func:`RiakBucket.get_binary <riak.bucket.RiakBucket.get_binary>`,
        in which case this will return a string.

        :rtype: array or string
        """
        return self._data

    def set_data(self, data):
        """
        Set the data stored in this object. This data will be
        JSON encoded unless the object was constructed with
        :func:`RiakBucket.new_binary <riak.bucket.RiakBucket.new_binary>` or
        :func:`RiakBucket.get_binary <riak.bucket.RiakBucket.get_binary>`,
        in which case it will be stored as a string.

        :param data: The data to store.
        :type data: mixed
        :rtype: data
        """
        self._data = data
        if MD_CTYPE not in self._metadata:
            if self._encode_data:
                self.set_content_type("application/json")
            else:
                self.set_content_type("application/octet-stream")
        return self

    def get_encoded_data(self):
        """
        Get the data encoded for storing
        """
        if self._encode_data == True:
            content_type = self.get_content_type()
            encoder = self._bucket.get_encoder(content_type)
            if encoder is None:
                if isinstance(self._data, basestring):
                    return self._data.encode()
                else:
                    raise RiakError("No encoder for non-string data "
                                    "with content type ${0}".
                                    format(content_type))
            else:
                return encoder(self._data)
        else:
            return self._data

    def set_encoded_data(self, data):
        """
        Set the object data from an encoded string. Make sure
        the metadata has been set correctly first.
        """
        if self._encode_data == True:
            content_type = self.get_content_type()
            decoder = self._bucket.get_decoder(content_type)
            if decoder is None:
                # if no decoder, just set as string data for application to handle
                self._data = data
            else:
                self._data = decoder(data)
        else:
            self._data = data
        return self


    def get_metadata(self):
        """
        Get the metadata stored in this object. Will return an associative
        array

        :rtype: dict
        """
        return self._metadata

    def set_metadata(self, metadata):
        """
        Set the metadata stored in this object.

        :param metadata: The data to store.
        :type metadata: dict
        :rtype: data
        """
        self._metadata = metadata
        return self

    def get_usermeta(self):
        if MD_USERMETA in self._metadata:
          return self._metadata[MD_USERMETA]
        else:
          return {}

    def set_usermeta(self, usermeta):
        """
        Sets the custom user metadata on this object. This doesn't include things
        like content type and links, but only user-defined meta attributes stored
        with the Riak object.

        :param userdata: The user metadata to store.
        :type userdata: dict
        :rtype: data
        """
        self._metadata[MD_USERMETA] = usermeta
        return self

    def add_index(self, field, value):
        """
        Tag this object with the specified field/value pair for indexing.

        :param field: The index field.
        :type field: string
        :param value: The index value.
        :type value: string or integer
        :rtype: self
        """
        rie = RiakIndexEntry(field, value)
        if not rie in self._metadata[MD_INDEX]:
            self._metadata[MD_INDEX].append(rie)

        return self

    def remove_index(self, field, value):
        """
        Remove the specified field/value pair as an index on this object.

        :param field: The index field.
        :type field: string
        :param value: The index value.
        :type value: string or integer
        :rtype: self
        """
        rie = RiakIndexEntry(field, value)
        if rie in self._metadata[MD_INDEX]:
            self._metadata[MD_INDEX].remove(rie)
        return self

    def get_indexes(self, field = None):
        """
        Get a list of the index entries for this object. If a field is provided, returns a list 

        :param field: The index field.
        :type field: string or None
        :rtype: (array of RiakIndexEntry) or (array of string or integer)
        """
        if field == None:
            return self._metadata[MD_INDEX]
        else:
            return [x.get_value() for x in self._metadata[MD_INDEX] if x.get_field() == field]

    def exists(self):
        """
        Return True if the object exists, False otherwise. Allows you to
        detect a :func:`RiakBucket.get <riak.bucket.RiakBucket.get>` or
        :func:`RiakBucket.get_binary <riak.bucket.RiakBucket.get_binary>`
        operation where the object is missing.

        :rtype: boolean
        """
        return self._exists

    def get_content_type(self):
        """
        Get the content type of this object. This is either ``application/json``, or
        the provided content type if the object was created via
        :func:`RiakBucket.new_binary <riak.bucket.RiakBucket.new_binary>`.

        :rtype: string
        """
        return self._metadata[MD_CTYPE]

    def set_content_type(self, content_type):
        """
        Set the content type of this object.

        :param content_type: The new content type.
        :type content_type: string
        :rtype: self
        """
        self._metadata[MD_CTYPE] = content_type
        return self

    def add_link(self, obj, tag=None):
        """
        Add a link to a RiakObject.

        :param obj: Either a RiakObject or a RiakLink object.
        :type obj: mixed
        :param tag: Optional link tag. Defaults to bucket name. It is ignored
            if ``obj`` is a RiakLink instance.
        :type tag: string
        :rtype: RiakObject
        """
        if isinstance(obj, RiakLink):
            newlink = obj
        else:
            newlink = RiakLink(obj._bucket._name, obj._key, tag)

        self.remove_link(newlink)
        links = self._metadata[MD_LINKS]
        links.append(newlink)
        return self

    def remove_link(self, obj, tag=None):
        """
        Remove a link to a RiakObject.

        :param obj: Either a RiakObject or a RiakLink object.
        :type obj: mixed
        :param tag: Optional link tag. Defaults to bucket name. It is ignored
            if ``obj`` is a RiakLink instance.
        :type tag: string
        :rtype: self
        """
        if isinstance(obj, RiakLink):
            oldlink = obj
        else:
            oldlink = RiakLink(obj._bucket._name, obj._key, tag)

        a = []
        links = self._metadata.get(MD_LINKS, [])
        for link in links:
            if not link.isEqual(oldlink):
                a.append(link)

        self._metadata[MD_LINKS] = a
        return self

    def get_links(self):
        """
        Return an array of RiakLink objects.

        :rtype: array()
        """
        # Set the clients before returning...
        if MD_LINKS in self._metadata:
            links = self._metadata[MD_LINKS]
            for link in links:
                link._client = self._client
            return links
        else:
            return []

    def store(self, w=None, dw=None, return_body=True):
        """
        Store the object in Riak. When this operation completes, the
        object could contain new metadata and possibly new data if Riak
        contains a newer version of the object according to the object's
        vector clock.

        :param w: W-value, wait for this many partitions to respond
         before returning to client.
        :type w: integer
        :param dw: DW-value, wait for this many partitions to
         confirm the write before returning to client.
        :type dw: integer
        :param return_body: if the newly stored object should be retrieved
        :type return_body: bool
        :rtype: self
        """
        # Use defaults if not specified...
        w = self._bucket.get_w(w)
        dw = self._bucket.get_dw(dw)

        # Issue the get over our transport
        t = self._client.get_transport()
        Result = t.put(self, w, dw, return_body)
        if Result is not None:
            self.populate(Result)

        return self


    def reload(self, r=None, vtag=None):
        """
        Reload the object from Riak. When this operation completes, the
        object could contain new metadata and a new value, if the object
        was updated in Riak since it was last retrieved.

        :param r: R-Value, wait for this many partitions to respond
         before returning to client.
        :type r: integer
        :rtype: self
        """
        # Do the request...
        r = self._bucket.get_r(r)
        t = self._client.get_transport()
        Result = t.get(self, r, vtag)

        self.clear()
        if Result is not None:
            self.populate(Result)

        return self


    def delete(self, rw=None):
        """
        Delete this object from Riak.

        :param rw: RW-value. Wait until this many partitions have
            deleted the object before responding.
        :type rw: integer
        :rtype: self
        """
        # Use defaults if not specified...
        rw = self._bucket.get_rw(rw)
        t = self._client.get_transport()
        Result = t.delete(self, rw)
        self.clear()
        return self

    def clear(self) :
        """
        Reset this object.

        :rtype: self
        """
        self._headers = []
        self._links = []
        self._data = None
        self._exists = False
        self._siblings = []
        return self

    def vclock(self) :
        """
        Get the vclock of this object.

        :rtype: string
        """
        return self._vclock

    def populate(self, Result) :
        """
        Populate the object based on the return from get.

        If None returned, then object is not found
        If a tuple of vclock, contents then one or more
        whole revisions of the key were found
        If a list of vtags is returned there are multiple
        sibling that need to be retrieved with get.
        """
        self.clear()
        if Result is None:
            return self
        elif type(Result) == types.ListType:
            self.set_siblings(Result)
        elif type(Result) == types.TupleType:
            (vclock, contents) = Result
            self._vclock = vclock
            if len(contents) > 0:
                (metadata, data) = contents.pop(0)
                self._exists = True
                self.set_metadata(metadata)
                self.set_encoded_data(data)
                # Create objects for all siblings
                siblings = [self]
                for (metadata, data) in contents:
                    sibling = copy.copy(self)
                    sibling.set_metadata(metadata)
                    sibling.set_encoded_data(data)
                    siblings.append(sibling)
                for sibling in siblings:
                    sibling.set_siblings(siblings)
        else:
            raise RiakError("do not know how to handle type " + str(type(Result)))

    def has_siblings(self):
        """
        Return True if this object has siblings.

        :rtype: boolean
        """
        return(self.get_sibling_count() > 0)

    def get_sibling_count(self):
        """
        Get the number of siblings that this object contains.

        :rtype: integer
        """
        return len(self._siblings)

    def get_sibling(self, i, r=None):
        """
        Retrieve a sibling by sibling number.

        :param i: Sibling number.
        :type i: integer
        :param r: R-Value. Wait until this many partitions
            have responded before returning to client.
        :type r: integer
        :rtype: RiakObject.
        """
        if isinstance(self._siblings[i], RiakObject):
            return self._siblings[i]
        else:
            # Use defaults if not specified.
            r = self._bucket.get_r(r)

            # Run the request...
            vtag = self._siblings[i]
            obj = RiakObject(self._client, self._bucket, self._key)
            obj.reload(r, vtag)

            # And make sure it knows who it's siblings are
            self._siblings[i] = obj
            obj.set_siblings(self._siblings)
            return obj

    def get_siblings(self, r=None):
        """
        Retrieve an array of siblings.

        :param r: R-Value. Wait until this many partitions have
            responded before returning to client.
        :type r: integer
        :rtype: array of RiakObject
        """
        a = []
        for i in range(self.get_sibling_count()):
            a.append(self.get_sibling(i, r))
        return a

    def set_siblings(self, siblings):
        """
        Set the array of siblings - used internally

        .. warning::

            Make sure this object is at index 0 so get_siblings(0) always returns
            the current object
        """
        try:
            i = siblings.index(self)
            if i != 0:
                siblings.pop(i)
                siblings.insert(0, self)
        except ValueError:
            pass

        if len(siblings) > 1:
            self._siblings = siblings
        else:
            self._siblings = []

    def add(self, *args):
        """
        Start assembling a Map/Reduce operation.
        A shortcut for :func:`RiakMapReduce.add`.

        :rtype: RiakMapReduce
        """
        mr = RiakMapReduce(self._client)
        mr.add(self._bucket._name, self._key)
        return apply(mr.add, args)

    def link(self, *args):
        """
        Start assembling a Map/Reduce operation.
        A shortcut for :func:`RiakMapReduce.link`.

        :rtype: RiakMapReduce
        """
        mr = RiakMapReduce(self._client)
        mr.add(self._bucket._name, self._key)
        return apply(mr.link, args)

    def map(self, *args):
        """
        Start assembling a Map/Reduce operation.
        A shortcut for :func:`RiakMapReduce.map`.

        :rtype: RiakMapReduce
        """
        mr = RiakMapReduce(self._client)
        mr.add(self._bucket._name, self._key)
        return apply(mr.map, args)

    def reduce(self, params):
        """
        Start assembling a Map/Reduce operation.
        A shortcut for :func:`RiakMapReduce.reduce`.

        :rtype: RiakMapReduce
        """
        mr = RiakMapReduce(self._client)
        mr.add(self._bucket._name, self._key)
        return apply(mr.reduce, params)

from mapreduce import *
