# encoding: utf-8

import pytest

from ..test_common import skipifdev
from ..test_common.test_kraken import (_test_stop_restart_kraken,
                                       _test_stop_start_apache,
                                       _test_test_kraken_nowait_nofail
                                       )
from ..utils import get_running_krakens


@skipifdev
def test_kraken_setup(single):
    platform, fabric = single
    assert platform.path_exists('/etc/init.d/kraken_default')
    assert platform.path_exists('/srv/kraken/default/kraken.ini')
    assert platform.path_exists('/etc/jormungandr.d/default.json')


nominal_krakens = {'host': {'default'}}
krakens_after_stop = {'host': set()}


@skipifdev
def test_stop_restart_single_kraken(single):
    _test_stop_restart_kraken(single,
                             map_start=nominal_krakens,
                             map_stop=krakens_after_stop,
                             stop_pat=('stop_kraken', ('default',)),
                             start_pat=('component.kraken.restart_kraken', ('default',), dict(test=False))
                             )


@skipifdev
def test_restart_all_krakens(single):
    _test_stop_restart_kraken(single,
                             map_start=nominal_krakens,
                             map_stop=krakens_after_stop,
                             stop_pat=('stop_kraken', ('default',)),
                             start_pat=('restart_all_krakens', (), dict(wait=False))
                             )


@skipifdev
def test_stop_require_start_kraken(single):
    _test_stop_restart_kraken(single,
                             map_start=nominal_krakens,
                             map_stop=krakens_after_stop,
                             stop_pat=('stop_kraken', ('default',)),
                             start_pat=('require_kraken_started', ('default',), {}),
                             )


@skipifdev
def test_require_all_krakens_started(single):
    _test_stop_restart_kraken(single,
                             map_start=nominal_krakens,
                             map_stop=krakens_after_stop,
                             stop_pat=('stop_kraken', ('default',)),
                             start_pat=('require_all_krakens_started', (), {}),
                             )


@skipifdev
def test_stop_start_apache(single):
    _test_stop_start_apache(single, ('host',))


@skipifdev
def test_test_kraken_nowait_nofail(single, capsys):
    _test_test_kraken_nowait_nofail(single, capsys, map={'host': {'default'}}, ret_val=False)


# @skipifdev
# This test is temporarily removed because I don't know yet how to restart fabric connections
# that are closed when an exception is raised below
# def test_check_dead_instances(single, capsys):
#     single, fabric = single
#     # make sure that krakens are started
#     fabric.execute('require_all_krakens_started')
#     time.sleep(1)
#
#     with pytest.raises(SystemExit):
#         fabric.execute('component.kraken.check_dead_instances')
#     out, err = capsys.readouterr()
#     assert 'http://{}:80/monitor-kraken/?instance=default'.format(single.get_hosts().values()[0]) in out
#     assert 'The threshold of allowed dead instances is exceeded: Found 1 dead instances out of 1.' in out


# @skipifdev
def test_create_remove_eng_instance(single, capsys):
    platform, fabric = single
    fabric.get_object('instance.add_instance')('toto', 'passwd')
    fabric.execute('create_eng_instance', 'toto')
    out, err = capsys.readouterr()
    assert 'INFO: kraken toto instance is running on {}'.format(platform.get_hosts()['host']) in out
    assert platform.path_exists('/srv/kraken/toto/kraken.ini', 'host')
    assert platform.path_exists('/etc/init.d//kraken_toto', 'host')
    assert platform.path_exists('/var/log/kraken/toto.log', 'host')
    assert set(get_running_krakens(platform, 'host')) == {'default', 'toto'}
    fabric.execute('remove_kraken_instance', 'toto', purge_logs=True)
    assert platform.path_exists('/srv/kraken/toto/kraken.ini', 'host', negate=True)
    assert platform.path_exists('/etc/init.d//kraken_toto', 'host', negate=True)
    assert platform.path_exists('/var/log/kraken/toto.log', 'host', negate=True)
    assert get_running_krakens(platform, 'host') == ['default']
