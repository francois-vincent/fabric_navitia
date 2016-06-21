# encoding: utf-8

import time

from ..test_common import skipifdev
from ..test_common.test_kraken import (_test_stop_restart_kraken,
                                       _test_stop_start_apache,
                                       _test_test_kraken_nowait_nofail,
                                       )
from ..utils import get_running_krakens


SHOW_CALL_TRACKER_DATA = False
nominal_krakens = {'host1': {'us-wa', 'fr-nw', 'fr-npdc', 'fr-ne-amiens', 'fr-idf', 'fr-cen'},
                   'host2': {'us-wa', 'fr-nw', 'fr-npdc', 'fr-ne-amiens', 'fr-idf', 'fr-cen'}}
krakens_after_stop = {'host1': {'fr-nw', 'fr-npdc', 'fr-idf', 'fr-cen'},
                      'host2': {'fr-nw', 'fr-npdc', 'fr-idf', 'fr-cen'}}


@skipifdev
def test_kraken_setup(duplicated):
    platform, fabric = duplicated
    for krak in fabric.env.instances:
        assert platform.path_exists('/etc/init.d/kraken_{}'.format(krak))
        assert platform.path_exists('/srv/kraken/{}/kraken.ini'.format(krak))
        assert platform.path_exists('/etc/jormungandr.d/{}.json'.format(krak), 'host1')
        assert platform.path_exists('/etc/jormungandr.d/{}.json'.format(krak), 'host2', negate=True)
        assert platform.path_exists('/var/log/kraken/{}.log'.format(krak))


@skipifdev
def test_stop_restart_single_kraken(duplicated):
    _test_stop_restart_kraken(duplicated,
                             map_start=nominal_krakens,
                             map_stop=krakens_after_stop,
                             stop_pat=('stop_kraken', ('us-wa', 'fr-ne-amiens')),
                             start_pat=('component.kraken.restart_kraken', ('us-wa', 'fr-ne-amiens'), dict(test=False))
                             )


@skipifdev
def test_restart_all_krakens(duplicated):
    _test_stop_restart_kraken(duplicated,
                             map_start=nominal_krakens,
                             map_stop=krakens_after_stop,
                             stop_pat=('stop_kraken', ('us-wa', 'fr-ne-amiens')),
                             start_pat=('restart_all_krakens', (), dict(wait=False))
                             )


@skipifdev
def test_stop_require_start_kraken(duplicated):
    _test_stop_restart_kraken(duplicated,
                             map_start=nominal_krakens,
                             map_stop=krakens_after_stop,
                             stop_pat=('stop_kraken', ('us-wa', 'fr-ne-amiens')),
                             start_pat=('require_kraken_started', ('us-wa', 'fr-ne-amiens'), {}),
                             )


@skipifdev
def test_require_all_krakens_started(duplicated):
    _test_stop_restart_kraken(duplicated,
                             map_start=nominal_krakens,
                             map_stop=krakens_after_stop,
                             stop_pat=('stop_kraken', ('us-wa', 'fr-ne-amiens')),
                             start_pat=('require_all_krakens_started', (), {}),
                             )


@skipifdev
def test_stop_start_apache(duplicated):
    _test_stop_start_apache(duplicated, ('host1', 'host2'))


@skipifdev
def test_test_kraken_nowait_nofail(duplicated, capsys):
    # wait for krakens to be fully started
    time.sleep(15)
    _test_test_kraken_nowait_nofail(duplicated, capsys,
                                    map={'host1': {'us-wa'}, 'host2': {'fr-ne-amiens'}}, ret_val=None)


@skipifdev
def test_get_no_data_instances(duplicated, capsys):
    platform, fabric = duplicated
    fabric.execute('component.kraken.get_no_data_instances')
    out, err = capsys.readouterr()
    for instance in fabric.env.instances:
        assert "NOTICE: no data for {}, append it to exclude list".format(instance) in out
    assert set(fabric.env.excluded_instances) == set(fabric.env.instances)


@skipifdev
def test_test_all_krakens_no_wait(duplicated):
    platform, fabric = duplicated
    time.sleep(15)
    value, exception, stdout, stderr = fabric.execute_forked('test_all_krakens')
    for instance in fabric.env.instances:
        assert stdout.count("WARNING: instance {} has no loaded data".format(instance)) == 2


@skipifdev
def test_check_dead_instances(duplicated):
    platform, fabric = duplicated
    value, exception, stdout, stderr = fabric.execute_forked('component.kraken.check_dead_instances')
    assert value is None
    assert isinstance(exception, SystemExit)
    assert 'The threshold of allowed dead instances is exceeded: ' \
           'Found 12 dead instances out of 6.' in stdout


@skipifdev
def test_create_remove_eng_instance(duplicated):
    platform, fabric = duplicated
    fabric.get_object('instance.add_instance')('toto', 'passwd',
                       zmq_socket_port=30004, zmq_server=(fabric.env.host1_ip, fabric.env.host2_ip))

    with fabric.set_call_tracker('component.kraken.update_eng_instance_conf') as data:
        value, exception, stdout, stderr = fabric.execute_forked('create_eng_instance', 'toto')

    if SHOW_CALL_TRACKER_DATA:
        from pprint import pprint
        pprint(dict(data()))
    # there is only one call to update_eng_instance_conf
    assert len(data()['update_eng_instance_conf']) == 2
    host1_string = 'root@{}'.format(platform.get_hosts()['host1'])
    host2_string = 'root@{}'.format(platform.get_hosts()['host2'])
    # first parameter is the newly created instance
    assert data()['update_eng_instance_conf'][0][0][0].name == 'toto'
    assert data()['update_eng_instance_conf'][1][0][0].name == 'toto'
    # second parameter is the host string
    assert set(x[0][1]for x in data()['update_eng_instance_conf']) == {host1_string, host2_string}

    time.sleep(2)
    assert 'INFO: kraken toto instance is running on {}'.format(platform.get_hosts()['host1']) in stdout
    assert 'INFO: kraken toto instance is running on {}'.format(platform.get_hosts()['host2']) in stdout
    assert platform.path_exists('/srv/kraken/toto/kraken.ini')
    assert platform.path_exists('/etc/init.d//kraken_toto')
    assert platform.path_exists('/var/log/kraken/toto.log')
    # check that new kraken is running on both hosts
    assert set(get_running_krakens(platform, 'host1')) == {'toto'} | nominal_krakens['host1']
    assert set(get_running_krakens(platform, 'host2')) == {'toto'} | nominal_krakens['host2']

    fabric.execute('remove_kraken_instance', 'toto', purge_logs=True)
    assert platform.path_exists('/srv/kraken/toto/kraken.ini', negate=True)
    assert platform.path_exists('/etc/init.d//kraken_toto', negate=True)
    assert platform.path_exists('/var/log/kraken/toto.log', negate=True)
    assert set(get_running_krakens(platform, 'host1')) == nominal_krakens['host1']
    assert set(get_running_krakens(platform, 'host2')) == nominal_krakens['host2']


# @skipifdev
def test_restart_all_krakens_alternate(duplicated):
    platform, fabric = duplicated

    fabric.env.excluded_instances = ['us-wa', 'fr-nw']
    with fabric.set_call_tracker('component.kraken.require_monitor_kraken_started',
                                 'component.kraken.restart_kraken_on_host') as data:
        value, exception, stdout, stderr = fabric.execute_forked('component.kraken.restart_all_krakens', wait=False)

    if SHOW_CALL_TRACKER_DATA:
        from pprint import pprint
        pprint(dict(data()))
    assert len(data()['require_monitor_kraken_started']) == 2
    # call to restart_kraken is not dependant on env.excluded_instances
    # every kraken must be restarted
    assert len(data()['restart_kraken_on_host']) == 12

    host1 = platform.get_hosts()['host1']
    host2 = platform.get_hosts()['host2']
    for instance in fabric.env.excluded_instances:
        assert stdout.count("{} has no data, not testing it".format(instance)) == 1
    for instance in set(fabric.env.instances).difference(fabric.env.excluded_instances):
        assert stdout.count('calling : http://{}:80/monitor-kraken/?instance={}'
                            .format(host1, instance)) == 1
        assert stdout.count('calling : http://{}:80/monitor-kraken/?instance={}'
                            .format(host2, instance)) == 1
        assert stdout.count('OK: instance {} has correct values:'.format(instance)) == 2


@skipifdev
def test_redeploy_kraken_swap(duplicated, capsys):
    platform, fabric = duplicated
    add_instance = fabric.get_object('instance.add_instance')

    # set instance on one eng machine
    add_instance('toto', 'passwd', zmq_socket_port=30004, zmq_server=fabric.env.host1_ip)
    fabric.execute('create_eng_instance', 'toto')

    # change zmq_server to other eng machine
    add_instance('toto', 'passwd', zmq_socket_port=30004, zmq_server=fabric.env.host2_ip)
    # TODO fix that, it freezes ! (paramiko bug)
    # with fabric.set_call_tracker('component.kraken.create_eng_instance',
    #                              'component.kraken.remove_kraken_instance') as data:
    #     value, exception, stdout, stderr = fabric.execute_forked('redeploy_kraken', 'toto')
    fabric.execute('redeploy_kraken', 'toto')

    stdout, stderr = capsys.readouterr()
    assert 'INFO: kraken toto instance is starting on {}'.format(platform.get_hosts()['host2']) in stdout
    assert 'INFO: kraken toto instance is running on {}'.format(platform.get_hosts()['host2']) in stdout
    assert 'INFO: removing kraken instance toto from {}'.format(platform.get_hosts()['host1']) in stdout
    assert platform.path_exists('/srv/kraken/toto/kraken.ini', 'host2')
    assert platform.path_exists('/etc/init.d//kraken_toto', 'host2')
    assert platform.path_exists('/var/log/kraken/toto.log', 'host2')
    assert platform.path_exists('/srv/kraken/toto/kraken.ini', 'host1', negate=True)
    assert platform.path_exists('/etc/init.d//kraken_toto', 'host1', negate=True)
    assert platform.path_exists('/var/log/kraken/toto.log', 'host1', negate=True)
    # check that moved kraken is running on host1 but not host2
    time.sleep(2)
    assert set(get_running_krakens(platform, 'host1')) == nominal_krakens['host1']
    assert set(get_running_krakens(platform, 'host2')) == {'toto'} | nominal_krakens['host2']


@skipifdev
def test_redeploy_kraken_reduce(duplicated, capsys):
    platform, fabric = duplicated
    add_instance = fabric.get_object('instance.add_instance')

    # set instance on all eng machines
    add_instance('toto', 'passwd', zmq_socket_port=30004)
    fabric.execute('create_eng_instance', 'toto')

    # change zmq_server to other eng machine
    add_instance('toto', 'passwd', zmq_socket_port=30004, zmq_server=fabric.env.host2_ip)
    # TODO fix that, it freezes ! (paramiko bug)
    # with fabric.set_call_tracker('component.kraken.create_eng_instance',
    #                              'component.kraken.remove_kraken_instance') as data:
    #     value, exception, stdout, stderr = fabric.execute_forked('redeploy_kraken', 'toto')
    fabric.execute('redeploy_kraken', 'toto')

    stdout, stderr = capsys.readouterr()
    assert 'INFO: kraken toto instance is running on {}'.format(platform.get_hosts()['host2']) in stdout
    assert 'INFO: removing kraken instance toto from {}'.format(platform.get_hosts()['host1']) in stdout
    assert platform.path_exists('/srv/kraken/toto/kraken.ini', 'host2')
    assert platform.path_exists('/etc/init.d//kraken_toto', 'host2')
    assert platform.path_exists('/var/log/kraken/toto.log', 'host2')
    assert platform.path_exists('/srv/kraken/toto/kraken.ini', 'host1', negate=True)
    assert platform.path_exists('/etc/init.d//kraken_toto', 'host1', negate=True)
    assert platform.path_exists('/var/log/kraken/toto.log', 'host1', negate=True)
    # check that moved kraken is running on host1 but not host2
    time.sleep(2)
    assert set(get_running_krakens(platform, 'host1')) == nominal_krakens['host1']
    assert set(get_running_krakens(platform, 'host2')) == {'toto'} | nominal_krakens['host2']


@skipifdev
def test_redeploy_all_krakens(duplicated, capsys):
    platform, fabric = duplicated

    fabric.execute('redeploy_all_krakens')

    stdout, stderr = capsys.readouterr()
    host1 = platform.get_hosts()['host1']
    host2 = platform.get_hosts()['host2']
    for instance in fabric.env.instances:
        assert 'INFO: kraken {} instance is running on {}'.format(instance, host1) in stdout
        assert 'INFO: kraken {} instance is running on {}'.format(instance, host2) in stdout
