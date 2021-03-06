# -*- coding: utf-8 -*-


from wakatime.main import execute
from wakatime.packages import requests

import logging
import os
import time
import shutil
from testfixtures import log_capture
from wakatime.compat import u
from wakatime.constants import SUCCESS
from wakatime.exceptions import NotYetImplemented
from wakatime.dependencies import DependencyParser, TokenParser
from wakatime.packages.pygments.lexers import ClassNotFound, PythonLexer
from wakatime.packages.requests.models import Response
from wakatime.stats import get_lexer_by_name
from . import utils
from .utils import ANY


class DependenciesTestCase(utils.TestCase):
    patch_these = [
        'wakatime.packages.requests.adapters.HTTPAdapter.send',
        'wakatime.offlinequeue.Queue.push',
        ['wakatime.offlinequeue.Queue.pop', None],
        ['wakatime.offlinequeue.Queue.connect', None],
        'wakatime.session_cache.SessionCache.save',
        'wakatime.session_cache.SessionCache.delete',
        ['wakatime.session_cache.SessionCache.get', requests.session],
        ['wakatime.session_cache.SessionCache.connect', None],
    ]

    def shared(self, expected_dependencies=[], expected_language=ANY, expected_lines=ANY, entity='', config='good_config.cfg', extra_args=[]):
        response = Response()
        response.status_code = 201
        self.patched['wakatime.packages.requests.adapters.HTTPAdapter.send'].return_value = response

        config = os.path.join('tests/samples/configs', config)

        with utils.TemporaryDirectory() as tempdir:
            shutil.copy(os.path.join('tests/samples/codefiles', entity), os.path.join(tempdir, os.path.basename(entity)))
            entity = os.path.realpath(os.path.join(tempdir, os.path.basename(entity)))

            now = u(int(time.time()))
            args = ['--file', entity, '--config', config, '--time', now] + extra_args

            retval = execute(args)
            self.assertEquals(retval, SUCCESS)
            self.assertNothingPrinted()

            heartbeat = {
                'language': expected_language,
                'lines': expected_lines,
                'entity': os.path.realpath(entity),
                'project': ANY,
                'branch': ANY,
                'dependencies': expected_dependencies,
                'time': float(now),
                'type': 'file',
                'is_write': False,
                'user_agent': ANY,
            }
            self.assertHeartbeatSent(heartbeat)

            self.assertHeartbeatNotSavedOffline()
            self.assertOfflineHeartbeatsSynced()
            self.assertSessionCacheSaved()

    def test_token_parser(self):
        with self.assertRaises(NotYetImplemented):
            source_file = 'tests/samples/codefiles/c_only/non_empty.h'
            parser = TokenParser(source_file)
            parser.parse()

        with utils.mock.patch('wakatime.dependencies.TokenParser._extract_tokens') as mock_extract_tokens:
            source_file = 'tests/samples/codefiles/see.h'
            parser = TokenParser(source_file)
            parser.tokens
            mock_extract_tokens.assert_called_once_with()

        parser = TokenParser(None)
        parser.append('one.two.three', truncate=True, truncate_to=1)
        parser.append('one.two.three', truncate=True, truncate_to=2)
        parser.append('one.two.three', truncate=True, truncate_to=3)
        parser.append('one.two.three', truncate=True, truncate_to=4)

        expected = [
            'one',
            'one.two',
            'one.two.three',
            'one.two.three',
        ]
        self.assertEquals(parser.dependencies, expected)

    @log_capture()
    def test_dependency_parser(self, logs):
        logging.disable(logging.NOTSET)

        lexer = PythonLexer
        lexer.__class__.__name__ = 'FooClass'
        parser = DependencyParser(None, lexer)

        dependencies = parser.parse()

        log_output = u("\n").join([u(' ').join(x) for x in logs.actual()])
        self.assertEquals(log_output, '')

        self.assertNothingPrinted()

        expected = []
        self.assertEquals(dependencies, expected)

    @log_capture()
    def test_missing_dependency_parser_in_debug_mode(self, logs):
        logging.disable(logging.NOTSET)

        # turn on debug mode
        log = logging.getLogger('WakaTime')
        log.setLevel(logging.DEBUG)

        lexer = PythonLexer
        lexer.__class__.__name__ = 'FooClass'
        parser = DependencyParser(None, lexer)

        # parse dependencies
        dependencies = parser.parse()

        log_output = u("\n").join([u(' ').join(x) for x in logs.actual()])
        expected = 'WakaTime DEBUG Parsing dependencies not supported for python.FooClass'
        self.assertEquals(log_output, expected)

        self.assertNothingPrinted()

        expected = []
        self.assertEquals(dependencies, expected)

    @log_capture()
    def test_missing_dependency_parser_importerror_in_debug_mode(self, logs):
        logging.disable(logging.NOTSET)

        # turn on debug mode
        log = logging.getLogger('WakaTime')
        log.setLevel(logging.DEBUG)

        with utils.mock.patch('wakatime.dependencies.import_module') as mock_import:
            mock_import.side_effect = ImportError('foo')

            lexer = PythonLexer
            lexer.__class__.__name__ = 'FooClass'
            parser = DependencyParser(None, lexer)

            # parse dependencies
            dependencies = parser.parse()

        log_output = u("\n").join([u(' ').join(x) for x in logs.actual()])
        expected = 'WakaTime DEBUG Parsing dependencies not supported for python.FooClass'
        self.assertEquals(log_output, expected)

        self.assertNothingPrinted()

        expected = []
        self.assertEquals(dependencies, expected)

    def test_io_error_suppressed_when_parsing_dependencies(self):
        with utils.mock.patch('wakatime.dependencies.open') as mock_open:
            mock_open.side_effect = IOError('')

            self.shared(
                expected_dependencies=[],
                expected_language='Python',
                expected_lines=37,
                entity='python.py',
            )

    def test_classnotfound_error_raised_when_passing_none_to_pygments(self):
        with self.assertRaises(ClassNotFound):
            get_lexer_by_name(None)

    def test_classnotfound_error_suppressed_when_parsing_dependencies(self):
        with utils.mock.patch('wakatime.stats.guess_lexer_using_filename') as mock_guess:
            mock_guess.return_value = (None, None)

            with utils.mock.patch('wakatime.stats.get_filetype_from_buffer') as mock_filetype:
                mock_filetype.return_value = 'foo'

                self.shared(
                    expected_dependencies=[],
                    expected_language=None,
                    expected_lines=37,
                    entity='python.py',
                )

    def test_python_dependencies_detected(self):
        self.shared(
            expected_dependencies=[
                'app',
                'django',
                'flask',
                'jinja',
                'mock',
                'pygments',
                'simplejson',
                'sqlalchemy',
                'unittest',
            ],
            expected_language='Python',
            expected_lines=37,
            entity='python.py',
        )

    def test_bower_dependencies_detected(self):
        self.shared(
            expected_dependencies=[
                'bootstrap',
                'bootstrap-daterangepicker',
                'moment',
                'moment-timezone',
                'bower',
                'animate.css',
            ],
            expected_language='JSON',
            expected_lines=11,
            entity='bower.json',
        )

    def test_grunt_dependencies_detected(self):
        self.shared(
            expected_dependencies=[
                'grunt',
            ],
            expected_language=None,
            expected_lines=23,
            entity='Gruntfile',
        )

    def test_java_dependencies_detected(self):
        self.shared(
            expected_dependencies=[
                'colorfulwolf.webcamapplet',
                'foobar',
            ],
            expected_language='Java',
            expected_lines=20,
            entity='java.java',
        )

    def test_c_dependencies_detected(self):
        self.shared(
            expected_dependencies=[
                'openssl',
            ],
            expected_language='C',
            expected_lines=8,
            entity='c_only/non_empty.c',
        )

    def test_cpp_dependencies_detected(self):
        self.shared(
            expected_dependencies=[
                'openssl',
            ],
            expected_language='C++',
            expected_lines=8,
            entity='c_and_cpp/non_empty.cpp',
        )

    def test_csharp_dependencies_detected(self):
        self.shared(
            expected_dependencies=[
                'Proper',
                'Fart',
                'Math',
                'WakaTime',
            ],
            expected_language='C#',
            expected_lines=18,
            entity='csharp/seesharp.cs',
        )

    def test_php_dependencies_detected(self):
        self.shared(
            expected_dependencies=[
                'Interop',
                'FooBarOne',
                'FooBarTwo',
                'FooBarThree',
                'FooBarFour',
                'FooBarSeven',
                'FooBarEight',
                'ArrayObject',
                "'ServiceLocator.php'",
                "'ServiceLocatorTwo.php'",
            ],
            expected_language='PHP',
            expected_lines=116,
            entity='php.php',
        )

    def test_php_in_html_dependencies_detected(self):
        self.shared(
            expected_dependencies=[
                '"https://maxcdn.bootstrapcdn.com/bootstrap/3.3.5/js/bootstrap.min.js"',
            ],
            expected_language='HTML+PHP',
            expected_lines=22,
            entity='html-with-php.html',
        )

    def test_html_django_dependencies_detected(self):
        self.shared(
            expected_dependencies=[
                '"libs/json2.js"',
            ],
            expected_language='HTML+Django/Jinja',
            expected_lines=40,
            entity='html-django.html',
        )

    def test_go_dependencies_detected(self):
        self.shared(
            expected_dependencies=[
                '"compress/gzip"',
                '"direct"',
                '"foobar"',
                '"github.com/golang/example/stringutil"',
                '"image/gif"',
                '"log"',
                '"math"',
                '"oldname"',
                '"os"',
                '"supress"',
            ],
            expected_language='Go',
            expected_lines=24,
            entity='go.go',
        )

    def test_dependencies_still_detected_when_alternate_language_used(self):
        with utils.mock.patch('wakatime.stats.smart_guess_lexer') as mock_guess_lexer:
            mock_guess_lexer.return_value = None

            self.shared(
                expected_dependencies=[
                    'app',
                    'django',
                    'flask',
                    'jinja',
                    'mock',
                    'pygments',
                    'simplejson',
                    'sqlalchemy',
                    'unittest',
                ],
                expected_language='Python',
                expected_lines=37,
                entity='python.py',
                extra_args=['--alternate-language', 'PYTHON'],
            )
