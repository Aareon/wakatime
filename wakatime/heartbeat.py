# -*- coding: utf-8 -*-
"""
    wakatime.heartbeat
    ~~~~~~~~~~~~~~~~~~
    :copyright: (c) 2017 Alan Hamlett.
    :license: BSD, see LICENSE for more details.
"""


import os
import logging
import re

from .compat import u, json
from .project import get_project_info
from .stats import get_file_stats
from .utils import get_user_agent, should_exclude, format_file_path


log = logging.getLogger('WakaTime')


class Heartbeat(object):
    """Heartbeat data for sending to API or storing in offline cache."""

    skip = False
    args = None
    configs = None

    time = None
    entity = None
    type = None
    is_write = None
    project = None
    branch = None
    language = None
    dependencies = None
    lines = None
    lineno = None
    cursorpos = None
    user_agent = None

    def __init__(self, data, args, configs, _clone=None):
        self.args = args
        self.configs = configs

        self.entity = data.get('entity')
        self.time = data.get('time', data.get('timestamp'))
        self.is_write = data.get('is_write')
        self.user_agent = data.get('user_agent') or get_user_agent(args.plugin)

        self.type = data.get('type', data.get('entity_type'))
        if self.type not in ['file', 'domain', 'app']:
            self.type = 'file'

        if not _clone:
            exclude = self._excluded_by_pattern()
            if exclude:
                self.skip = u('Skipping because matches exclude pattern: {pattern}').format(
                    pattern=u(exclude),
                )
                return
            if self.type == 'file':
                self.entity = format_file_path(self.entity)
            if self.type == 'file' and not os.path.isfile(self.entity):
                self.skip = u('File does not exist; ignoring this heartbeat.')
                return

            project, branch = get_project_info(configs, self, data)
            self.project = project
            self.branch = branch

            stats = get_file_stats(self.entity,
                                   entity_type=self.type,
                                   lineno=data.get('lineno'),
                                   cursorpos=data.get('cursorpos'),
                                   plugin=args.plugin,
                                   language=data.get('language'))
        else:
            self.project = data.get('project')
            self.branch = data.get('branch')
            stats = data

        for key in ['language', 'dependencies', 'lines', 'lineno', 'cursorpos']:
            if stats.get(key) is not None:
                setattr(self, key, stats[key])

    def update(self, attrs):
        """Return a copy of the current Heartbeat with updated attributes."""

        data = self.dict()
        data.update(attrs)
        heartbeat = Heartbeat(data, self.args, self.configs, _clone=True)
        heartbeat.skip = self.skip
        return heartbeat

    def sanitize(self):
        """Removes sensitive data including file names and dependencies.

        Returns a Heartbeat.
        """

        if not self.args.hidefilenames:
            return self

        if self.entity is None:
            return self

        if self.type != 'file':
            return self

        for pattern in self.args.hidefilenames:
            try:
                compiled = re.compile(pattern, re.IGNORECASE)
                if compiled.search(self.entity):

                    sanitized = {}
                    sensitive = ['dependencies', 'lines', 'lineno', 'cursorpos', 'branch']
                    for key, val in self.items():
                        if key in sensitive:
                            sanitized[key] = None
                        else:
                            sanitized[key] = val

                    extension = u(os.path.splitext(self.entity)[1])
                    sanitized['entity'] = u('HIDDEN{0}').format(extension)

                    return self.update(sanitized)

            except re.error as ex:
                log.warning(u('Regex error ({msg}) for include pattern: {pattern}').format(
                    msg=u(ex),
                    pattern=u(pattern),
                ))

        return self

    def json(self):
        return json.dumps(self.dict())

    def dict(self):
        return {
            'time': self.time,
            'entity': self.entity,
            'type': self.type,
            'is_write': self.is_write,
            'project': self.project,
            'branch': self.branch,
            'language': self.language,
            'dependencies': self.dependencies,
            'lines': self.lines,
            'lineno': self.lineno,
            'cursorpos': self.cursorpos,
            'user_agent': self.user_agent,
        }

    def items(self):
        return self.dict().items()

    def get_id(self):
        return u('{h.time}-{h.type}-{h.project}-{h.branch}-{h.entity}-{h.is_write}').format(
            h=self,
        )

    def _excluded_by_pattern(self):
        return should_exclude(self.entity, self.args.include, self.args.exclude)

    def __repr__(self):
        return self.json()

    def __bool__(self):
        return not self.skip

    def __nonzero__(self):
        return self.__bool__()

    def __getitem__(self, key):
        return self.dict()[key]
