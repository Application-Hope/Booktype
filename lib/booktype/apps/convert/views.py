# This file is part of Booktype.
# Copyright (c) 2013 Borko Jandras <borko.jandras@sourcefabric.org>
#
# Booktype is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Booktype is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with Booktype.  If not, see <http://www.gnu.org/licenses/>.

import os
import uuid

import celery

from django.views.generic.base import View
from django.http import HttpResponse, Http404
from django.conf import settings

from django.utils import simplejson as json

import sputnik

from . import tasks
from .utils.uploadhandler import FileUploadHandler


class OutputData(object):
    """Encapsulates information for a single conversion output."""

    def __init__(self, data):
        self.profile = data["profile"]
        self.config  = data["config"]
        self.output  = data["output"]


class RequestData(object):
    """Encapsulates all information specified by the conversion request."""

    @classmethod
    def parse(klass, text):
        return klass(json.loads(text))

    def __init__(self, data):
        self.assets  = data.get("assets", {}) # TODO: check type is dict
        self.input   = data["input"]
        self.outputs = {k: OutputData(v) for (k,v) in data["outputs"].iteritems()}


class ConvertView(View):
    def post(self, request):
        token = str(uuid.uuid1())

        # sandbox directory for this request
        base_path = os.path.join(settings.MEDIA_ROOT, "tmp", token)
        os.makedirs(base_path)

        request.upload_handlers = (FileUploadHandler(base_path), )

        # parse the request
        request_spec = get_request_spec(request)
        request_data = RequestData.parse(request_spec)

        # name:path for all uploaded files
        request_data.files = {field_name : file.file_path() for (field_name, file) in request.FILES.iteritems()}

        # start the task in the background
        async_result = tasks.convert.apply_async((request_data, base_path))
        task_id = map_task_id(async_result.task_id, token)

        response_data = {
            "state"   : async_result.state,
            "task_id" : task_id,
        }
        return HttpResponse(json.dumps(response_data), mimetype="application/json")

    def get(self, request, task_id):
        task_id = sputnik.rcon.get("convert:task_id:" + task_id)

        async_result = celery.current_app.AsyncResult(task_id)

        response_data = {
            "state"   : async_result.state,
            "result"  : str(async_result.result),
        }
        return HttpResponse(json.dumps(response_data), mimetype="application/json")


def get_request_spec(request):
    if request.POST:
        return request.POST["request-spec"]
    else:
        return request.body


def map_task_id(task_id, token):
    sputnik.rcon.set("convert:task_id:" + token, task_id)
    return token

def get_task_id(token):
    return sputnik.rcon.get("convert:task_id:" + token)


__all__ = ("ConvertView", )