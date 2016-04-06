# encoding: utf-8

import mock
import unittest

from fabric.api import env, execute
from requests.auth import HTTPBasicAuth
from requests.models import Response

from fabfile.component import jormungandr, tyr
from fabfile.instance import add_instance

from . import captured_output


def make_platform():
    # import fabfile.env.platforms
    env.tyr_base_destination_dir = '/srv/ed/data/'
    env.roledefs = {'tyr': ('host1', 'host2')}
    add_instance('toto', 'passwd')


def make_response(_content='', encoding='utf-8', status_code=200):
    response = Response()
    for k, v in locals().iteritems():
        setattr(response, k, v)
    return response


class TestTyr(unittest.TestCase):

    @mock.patch('fabfile.component.tyr.run')
    def test_remove_ed_instance(self, fabric_operations_run):
        make_platform()

        with captured_output() as (out, err):
            execute(tyr.remove_ed_instance, 'toto')

        self.assertEqual(fabric_operations_run.call_count, 6)
        run_calls = fabric_operations_run.mock_calls
        self.assertIn(mock.call('rm -rf /srv/ed/toto'), run_calls)
        self.assertIn(mock.call('rm -rf /srv/ed/toto/backup'), run_calls)
        # TODO: refactor code to remove redundant slash
        self.assertIn(mock.call('rm -rf /srv/ed/data//toto'), run_calls)
        self.assertEqual(err.getvalue(), '')
        self.assertIn("[host1] Executing task 'remove_ed_instance'", out.getvalue())
        self.assertIn("[host2] Executing task 'remove_ed_instance'", out.getvalue())


class TestJormun(unittest.TestCase):

    @mock.patch('requests.get', return_value=make_response(
        status_code=200,
        _content='{"message": "toto"}'
    ))
    def test_test_jormungandr_error_nofail(self, requests_get):
        env.jormungandr_url = 'toto.com'

        with captured_output() as (out, err):
            ret = jormungandr.test_jormungandr(env.jormungandr_url, fail_if_error=False)

        self.assertEqual(requests_get.call_count, 1)
        self.assertEqual(requests_get.call_args[0], ('http://toto.com/v1/coverage',))
        self.assertEqual(requests_get.call_args[1]['headers'], {'Host': 'toto.com'})
        self.assertIsInstance(requests_get.call_args[1]['auth'], HTTPBasicAuth)
        self.assertEqual(err.getvalue(), '')
        self.assertEqual(out.getvalue()[5:-6], "WARNING: Problem on result: '{u'message': u'toto'}")
        self.assertFalse(ret)

    @mock.patch('requests.get', return_value=make_response(
        status_code=200,
        _content='{"message": "toto"}'
    ))
    def test_test_jormungandr_error_fail(self, requests_get):
        env.jormungandr_url = 'toto.com'

        with self.assertRaises(SystemExit) as arc:
            with captured_output() as (out, err):
                jormungandr.test_jormungandr(env.jormungandr_url)
        self.assertEqual(arc.exception.args, (1,))
        self.assertEqual(err.getvalue(), '')
        self.assertEqual(out.getvalue()[5:-6], "CRITICAL: Problem on result: '{u'message': u'toto'}")


if __name__ == '__main__':
    unittest.main()
