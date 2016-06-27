# encoding: utf-8

import os.path
import time

import requests

from ..test_common import skipifdev
from ..utils import get_running_krakens

ROOTDIR = os.path.dirname(os.path.abspath(__file__))

instances_names = {'us-wa', 'fr-nw', 'fr-npdc', 'fr-ne-amiens', 'fr-idf', 'fr-cen'}


@skipifdev
def test_upgrade_kraken(duplicated):
    platform, fabric = duplicated

    with fabric.set_call_tracker('-component.kraken.upgrade_engine_packages',
                                 '-component.kraken.upgrade_monitor_kraken_packages',
                                 '-component.kraken.test_kraken',
                                 'component.kraken.restart_kraken_on_host',
                                 'component.kraken.require_monitor_kraken_started') as data:
        value, exception, stdout, stderr = fabric.execute_forked(
            'tasks.upgrade_kraken', up_confs=False, supervision=False)
    assert exception is None
    assert stderr == ''

    # upgrades apply on both machines
    assert len(data()['upgrade_engine_packages']) == 2
    assert len(data()['upgrade_monitor_kraken_packages']) == 2
    assert len(data()['require_monitor_kraken_started']) == 2
    assert len(data()['restart_kraken_on_host']) == 2 * len(fabric.env.instances)
    assert len(set((x[0][1] for x in data()['restart_kraken_on_host']))) == 2
    assert set((x[0][0].name for x in data()['restart_kraken_on_host'])) == instances_names
    for instance in fabric.env.instances:
        assert platform.docker_exec('readlink /srv/kraken/{}/kraken'.format(instance), 'host1') == '/usr/bin/kraken'
        assert platform.docker_exec('readlink /srv/kraken/{}/kraken'.format(instance), 'host2') == '/usr/bin/kraken'


@skipifdev
def test_upgrade_kraken_restricted(duplicated):
    platform, fabric = duplicated
    # patch the eng role (as done in upgrade_all on prod platform)
    fabric.env.roledefs['eng'] = fabric.env.eng_hosts_1

    with fabric.set_call_tracker('-component.kraken.upgrade_engine_packages',
                                 '-component.kraken.upgrade_monitor_kraken_packages',
                                 '-component.kraken.test_kraken',
                                 'component.kraken.restart_kraken_on_host',
                                 'component.kraken.require_monitor_kraken_started') as data:
        value, exception, stdout, stderr = fabric.execute_forked(
            'tasks.upgrade_kraken', up_confs=False, supervision=False)
    assert exception is None
    assert stderr == ''

    # upgrades apply only on restricted pool
    assert len(data()['upgrade_engine_packages']) == 1
    assert len(data()['upgrade_monitor_kraken_packages']) == 1
    assert len(data()['require_monitor_kraken_started']) == 1
    # kraken restart apply only on restricted pool
    assert len(data()['restart_kraken_on_host']) == len(fabric.env.instances)
    assert set((x[0][1] for x in data()['restart_kraken_on_host'])) == {fabric.env.eng_hosts_1[0]}
    assert set((x[0][0].name for x in data()['restart_kraken_on_host'])) == instances_names


@skipifdev
def test_upgrade_all_load_balancer(duplicated):
    platform, fabric = duplicated
    fabric.env.use_load_balancer = True
    # postgres is really long to warm up !
    time.sleep(15)

    # most of this test is unitary test: detailed functions are not called, they are traced
    with fabric.set_call_tracker('-tasks.check_last_dataset',
                                 '-tasks.upgrade_tyr',
                                 '-tasks.upgrade_kraken',
                                 '-tasks.upgrade_jormungandr',
                                 '-prod_tasks.disable_nodes',
                                 '-prod_tasks.enable_nodes',
                                 '-component.load_balancer._adc_connection',
                                 '-component.load_balancer.disable_node',
                                 '-component.load_balancer.enable_node') as data:
        value, exception, stdout, stderr = fabric.execute_forked('tasks.upgrade_all',
                       check_version=False, check_dead=False)
    assert exception is None
    assert stderr == ''

    assert stdout.count("Executing task 'stop_tyr_beat'") == 1
    assert stdout.count("Executing task 'start_tyr_beat'") == 1
    # 1 call to component.load_balancer.disable_node by reload_jormun_safe()
    assert len(data()['disable_node']) == 1
    # 1 call to component.load_balancer.enable_node by reload_jormun_safe()
    assert len(data()['enable_node']) == 1
    # 4 calls: 1 eng_hosts_1, 1 ws_hosts_1, 1 eng_hosts_2, 1 empty
    assert len(data()['disable_nodes']) == 4
    for i, x in enumerate((fabric.env.eng_hosts_1, fabric.env.ws_hosts_1, fabric.env.eng_hosts_2, [])):
        assert data()['disable_nodes'][i][0][0] == x
    # 3 calls: 1 eng_hosts_1, 1 ws_hosts_1, 1 eng_hosts_1
    assert len(data()['enable_nodes']) == 3
    for i, x in enumerate((fabric.env.eng_hosts_1, fabric.env.ws_hosts_1, fabric.env.eng_hosts)):
        assert data()['enable_nodes'][i][0][0] == x
    # 1 call in first phase with supervision, 1 call in second phase without supervision
    assert len(data()['upgrade_kraken']) == 2
    assert data()['upgrade_kraken'][0][1].get('supervision') is True
    assert data()['upgrade_kraken'][1][1].get('supervision') is None
    # 1 call in first phase, 1 call in second phase
    assert len(data()['upgrade_jormungandr']) == 2
    # only one phase
    assert len(data()['upgrade_tyr']) == 1


@skipifdev
def test_remove_instance(duplicated):
    platform, fabric = duplicated
    # postgres is really long to warm up !
    time.sleep(15)

    # set up a server for tyr API on host1 and start it
    platform.scp(os.path.join(ROOTDIR, 'tyr-api.conf'), '/etc/apache2/conf-enabled/tyr-api.conf', 'host1')
    platform.docker_exec('service apache2 restart', 'host1')
    assert requests.get('http://{}/v0/instances/us-wa'.format(fabric.env.tyr_url)).json()

    value, exception, stdout, stderr = fabric.execute_forked('tasks.remove_instance', 'us-wa')
    assert exception is None
    assert stderr == ''

    assert stdout.count("Executing task 'remove_postgresql_database'") == 1
    assert stdout.count("Executing task 'remove_ed_instance'") == 2
    assert stdout.count("Executing task 'remove_tyr_instance'") == 2
    assert stdout.count("Executing task 'remove_jormungandr_instance'") == 1

    assert requests.get('http://{}/v0/instances/us-wa'.format(fabric.env.tyr_url)).json() == []
    assert set(get_running_krakens(platform, 'host1')) == instances_names.difference(['us-wa'])
    assert set(get_running_krakens(platform, 'host2')) == instances_names.difference(['us-wa'])
    assert platform.path_exists('/srv/ed/us-wa', negate=True)
    assert platform.path_exists('/srv/ed/data/us-wa', negate=True)
    assert platform.path_exists('/srv/ed/data/us-wa/backup', negate=True)
    assert platform.path_exists('/etc/tyr.d/us-wa.ini', negate=True)
    assert platform.path_exists('/etc/init.d/kraken_us-wa', negate=True)
    assert platform.path_exists('/srv/kraken/us-wa', negate=True)
    assert platform.path_exists('/etc/jormungandr.d/us-wa.json', negate=True)


@skipifdev
def test_update_instance(duplicated):
    platform, fabric = duplicated
    # postgres is really long to warm up !
    time.sleep(15)

    # set up a server for tyr API on host1 and start it
    platform.scp(os.path.join(ROOTDIR, 'tyr-api.conf'), '/etc/apache2/conf-enabled/tyr-api.conf', 'host1')
    platform.docker_exec('service apache2 restart', 'host1')

    # create a new instance
    add_instance = fabric.get_object('instance.add_instance')
    add_instance('toto', 'passwd', zmq_socket_port=30004)

    with fabric.set_call_tracker('component.kraken.create_eng_instance',
                                 'component.jormungandr.deploy_jormungandr_instance_conf') as data:
        value, exception, stdout, stderr = fabric.execute_forked('tasks.update_instance', 'toto')
    assert exception is None

    max_sleep, step = 30, 5
    while max_sleep:
        max_sleep -= step
        time.sleep(step)
        if requests.get('http://{}/v0/instances/toto'.format(fabric.env.tyr_url)).json():
            break
    assert requests.get('http://{}/v0/instances/toto'.format(fabric.env.tyr_url)).json()[0]['name'] == 'toto'
    assert len(data()['create_eng_instance']) == 1
    assert len(data()['deploy_jormungandr_instance_conf']) == 1
