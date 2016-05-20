# encoding: utf-8

import time

from ..test_common import skipifdev
from ..test_common.test_kraken import (_test_stop_restart_kraken,
                                       _test_stop_start_apache,
                                       _test_test_kraken_nowait_nofail,
                                       )

from ..utils import get_running_krakens


@skipifdev
def test_kraken_setup(distributed):
    distributed, fabric = distributed
    for krak in ('us-wa', 'fr-nw', 'fr-npdc'):
        assert distributed.path_exists('/etc/init.d/kraken_{}'.format(krak), 'host1')
        assert distributed.path_exists('/etc/init.d/kraken_{}'.format(krak), 'host2', negate=True)
        assert distributed.path_exists('/etc/jormungandr.d/{}.json'.format(krak), 'host1')
        assert distributed.path_exists('/etc/jormungandr.d/{}.json'.format(krak), 'host2', negate=True)
        assert distributed.path_exists('/srv/kraken/{}/kraken.ini'.format(krak), 'host1')
        assert distributed.path_exists('/srv/kraken/{}/kraken.ini'.format(krak), 'host2', negate=True)
    for krak in ('fr-ne-amiens', 'fr-idf', 'fr-cen'):
        assert distributed.path_exists('/etc/init.d/kraken_{}'.format(krak), 'host2')
        assert distributed.path_exists('/etc/init.d/kraken_{}'.format(krak), 'host1', negate=True)
        assert distributed.path_exists('/etc/jormungandr.d/{}.json'.format(krak), 'host1')
        assert distributed.path_exists('/etc/jormungandr.d/{}.json'.format(krak), 'host2', negate=True)
        assert distributed.path_exists('/srv/kraken/{}/kraken.ini'.format(krak), 'host2')
        assert distributed.path_exists('/srv/kraken/{}/kraken.ini'.format(krak), 'host1', negate=True)


nominal_krakens = {'host1': {'us-wa', 'fr-nw', 'fr-npdc'}, 'host2': {'fr-ne-amiens', 'fr-idf', 'fr-cen'}}
krakens_after_stop = {'host1': {'fr-nw', 'fr-npdc'}, 'host2': {'fr-idf', 'fr-cen'}}
instances_names = {'us-wa', 'fr-nw', 'fr-npdc', 'fr-ne-amiens', 'fr-idf', 'fr-cen'}


@skipifdev
def test_stop_restart_single_kraken(distributed):
    _test_stop_restart_kraken(distributed,
                             map_start=nominal_krakens,
                             map_stop=krakens_after_stop,
                             stop_pat=('stop_kraken', ('us-wa', 'fr-ne-amiens')),
                             start_pat=('component.kraken.restart_kraken', ('us-wa', 'fr-ne-amiens'), dict(test=False))
                             )


@skipifdev
def test_restart_all_krakens(distributed):
    _test_stop_restart_kraken(distributed,
                             map_start=nominal_krakens,
                             map_stop=krakens_after_stop,
                             stop_pat=('stop_kraken', ('us-wa', 'fr-ne-amiens')),
                             start_pat=('restart_all_krakens', (), dict(wait=False))
                             )


@skipifdev
def test_stop_require_start_kraken(distributed):
    _test_stop_restart_kraken(distributed,
                             map_start=nominal_krakens,
                             map_stop=krakens_after_stop,
                             stop_pat=('stop_kraken', ('us-wa', 'fr-ne-amiens')),
                             start_pat=('require_kraken_started', ('us-wa', 'fr-ne-amiens'), {}),
                             )


@skipifdev
def test_require_all_krakens_started(distributed):
    _test_stop_restart_kraken(distributed,
                             map_start=nominal_krakens,
                             map_stop=krakens_after_stop,
                             stop_pat=('stop_kraken', ('us-wa', 'fr-ne-amiens')),
                             start_pat=('require_all_krakens_started', (), {}),
                             )


@skipifdev
def test_stop_start_apache(distributed):
    time.sleep(2)
    _, fabric = distributed
    with fabric.set_call_tracker('component.kraken.require_kraken_started') as data:
        _test_stop_start_apache(distributed, ('host1', 'host2'))
        # task require_kraken_started is called for each instance
        assert set((x[0][0].name for x in data()['require_kraken_started'])) == instances_names


@skipifdev
def test_test_kraken_nowait_nofail(distributed, capsys):
    time.sleep(15)
    _test_test_kraken_nowait_nofail(distributed, capsys,
                                    map={'host1': {'us-wa'}, 'host2': {'fr-ne-amiens'}}, ret_val=False)
# TODO https://ci.navitia.io/job/deploy_navitia_on_internal/35/console


@skipifdev
def test_get_no_data_instances(distributed, capsys):
    platform, fabric = distributed
    time.sleep(2)
    fabric.execute('component.kraken.get_no_data_instances')
    stdout, stderr = capsys.readouterr()
    assert stdout.count('NOTICE: ') == len(fabric.env.instances)
    for instance in fabric.env.instances:
        assert "NOTICE: no data for {}, append it to exclude list".format(instance) in stdout
    assert set(fabric.env.excluded_instances) == set(fabric.env.instances)


@skipifdev
def test_test_all_krakens_no_wait(distributed):
    platform, fabric = distributed
    # wait for krakens to be fully started
    time.sleep(15)
    value, exception, stdout, stderr = fabric.execute_forked('test_all_krakens')
    assert stdout.count('WARNING: ') == len(fabric.env.instances)
    for instance in fabric.env.instances:
        assert "WARNING: instance {} has no loaded data".format(instance) in stdout


@skipifdev
def test_check_dead_instances(distributed):
    platform, fabric = distributed
    value, exception, stdout, stderr = fabric.execute_forked('component.kraken.check_dead_instances')
    assert value is None
    assert isinstance(exception, SystemExit)
    assert 'The threshold of allowed dead instances is exceeded: ' \
           'Found 6 dead instances out of 6.' in stdout


# @skipifdev
def test_create_remove_eng_instance(distributed):
    platform, fabric = distributed
    fabric.get_object('instance.add_instance')('toto', 'passwd',
                       zmq_socket_port=30004, zmq_server=fabric.env.host1_ip)

    with fabric.set_call_tracker('component.kraken.update_eng_instance_conf') as data:
        value, exception, stdout, stderr = fabric.execute_forked('create_eng_instance', 'toto')
        # there is only one call to update_eng_instance_conf
        assert len(data()['update_eng_instance_conf']) == 1
        host_string = 'root@{}'.format(platform.get_hosts()['host1'])
        # first argument is the newly created instance
        assert data()['update_eng_instance_conf'][0][0][0].name == 'toto'
        # second argument is the host string
        assert data()['update_eng_instance_conf'][0][0][1] == host_string
        # host string is also set
        assert data()['update_eng_instance_conf'][0][-1] == host_string

    time.sleep(2)
    assert 'INFO: kraken toto instance is running on {}'.format(platform.get_hosts()['host1']) in stdout
    assert platform.path_exists('/srv/kraken/toto/kraken.ini', 'host1')
    assert platform.path_exists('/etc/init.d//kraken_toto', 'host1')
    assert platform.path_exists('/var/log/kraken/toto.log', 'host1')
    assert platform.path_exists('/srv/kraken/toto/kraken.ini', 'host2', negate=True)
    assert platform.path_exists('/etc/init.d//kraken_toto', 'host2', negate=True)
    assert platform.path_exists('/var/log/kraken/toto.log', 'host2', negate=True)
    assert set(get_running_krakens(platform, 'host1')) == {'toto'} | nominal_krakens['host1']
    assert set(get_running_krakens(platform, 'host2')) == nominal_krakens['host2']

    fabric.execute('remove_kraken_instance', 'toto', purge_logs=True)
    assert platform.path_exists('/srv/kraken/toto/kraken.ini', 'host1', negate=True)
    assert platform.path_exists('/etc/init.d//kraken_toto', 'host1', negate=True)
    assert platform.path_exists('/var/log/kraken/toto.log', 'host1', negate=True)
    assert set(get_running_krakens(platform, 'host1')) == nominal_krakens['host1']
    assert set(get_running_krakens(platform, 'host2')) == nominal_krakens['host2']
