# encoding: utf-8

import time

import pytest

from test_common import skipifdev
from test_common.test_kraken import _start_and_check_krakens


# @skipifdev
def test_test_jormun(platform, capsys):
    _start_and_check_krakens(platform, {'host': {'default'}})
    platform, fabric = platform

    assert fabric.execute('test_jormungandr', platform.get_hosts()['host'],
                          'default', fail_if_error=False).values()[0]
    out, err = capsys.readouterr()
    assert 'WARNING: Problem on result' not in out
    fabric.execute('stop_kraken', 'default')
    time.sleep(1)
    assert fabric.execute('test_jormungandr', platform.get_hosts()['host'],
                          'default', fail_if_error=False).values()[0] is False
    out, err = capsys.readouterr()
    assert "WARNING: Problem on result: '{u'message': u'The region %s is dead', u'error': " \
           "{u'message': u'The region %s is dead', u'id': u'dead_socket'}}'" % ('default', 'default') in out
    platform.ssh('service apache2 stop')
    time.sleep(1)
    with pytest.raises(SystemExit):
        fabric.execute('test_jormungandr', platform.get_hosts()['host'], 'default', fail_if_error=True)
