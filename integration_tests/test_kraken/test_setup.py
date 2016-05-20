# encoding: utf-8

from ..docker import docker_exec
from ..utils import filter_column, extract_column, python_requirements_compare
from ..test_common import skipifdev


@skipifdev
def test_update_monitor_configuration(distributed_undeployed):
    platform, fabric = distributed_undeployed
    # prepare required folder before test
    platform.docker_exec("mkdir -p /srv/monitor")
    fabric.execute('update_monitor_configuration')
    assert platform.path_exists('/srv/monitor/monitor.wsgi')
    assert platform.path_exists('/srv/monitor/settings.py')


@skipifdev
def test_setup_kraken(distributed_undeployed):
    platform, fabric = distributed_undeployed
    fabric.execute('setup_kraken')
    # check that user www-data exists
    assert filter_column(platform.get_data('/etc/passwd', 'host1'), 0, startswith='www-data')
    assert filter_column(platform.get_data('/etc/passwd', 'host2'), 0, startswith='www-data')
    # test existence of paths
    assert platform.path_exists('/srv/kraken')
    assert platform.path_exists('/srv/monitor')
    assert platform.path_exists('/var/log/kraken')
    # test that path belongs to www-data
    assert filter_column(platform.docker_exec('ls -ld /srv/kraken', 'host1'), 2, eq='www-data')
    assert filter_column(platform.docker_exec('ls -ld /srv/kraken', 'host2'), 2, eq='www-data')
    # check existence of monitor configuration
    assert platform.path_exists('/srv/monitor/monitor.wsgi')
    assert platform.path_exists('/srv/monitor/settings.py')
    # check apache configuration for monitor-kraken
    if fabric.env.distrib == 'debian7':
        assert platform.path_exists('/etc/apache2/conf.d/monitor-kraken')
    else:
        assert platform.path_exists('/etc/apache2/conf-available/monitor-kraken.conf')
    # check that apache is started
    assert 'apache2' in extract_column(platform.docker_exec('ps -A', 'host1'), -1, 1)
    assert 'apache2' in extract_column(platform.docker_exec('ps -A', 'host2'), -1, 1)


@skipifdev
def test_upgrade_engine_packages(distributed_undeployed):
    platform, fabric = distributed_undeployed
    fabric.execute('upgrade_engine_packages')
    assert platform.get_version('python', 'host1').startswith('2.7')
    assert platform.get_version('python', 'host2').startswith('2.7')
    assert docker_exec(platform.containers['host1'], 'pip -V', return_code_only=True) == 0
    assert docker_exec(platform.containers['host2'], 'pip -V', return_code_only=True) == 0
    if fabric.env.distrib == 'debian7':
        assert platform.get_version('libzmq-dev', 'host1')
        assert platform.get_version('libzmq-dev', 'host2')
    else:
        assert platform.get_version('libzmq3-dev', 'host1')
        assert platform.get_version('libzmq3-dev', 'host2')
    assert platform.get_version('navitia-kraken', 'host1')
    assert platform.get_version('navitia-kraken', 'host2')


@skipifdev
def test_upgrade_monitor_kraken_packages(distributed_undeployed):
    platform, fabric = distributed_undeployed
    fabric.execute('upgrade_monitor_kraken_packages')
    assert platform.get_version('navitia-monitor-kraken', 'host1')
    assert platform.get_version('navitia-monitor-kraken', 'host2')
    assert platform.path_exists('/usr/share/monitor_kraken/requirements.txt')
    known_missing = ['argparse==1.2.1', 'wsgiref==0.1.2']
    for host in ('host1', 'host2'):
        assert python_requirements_compare(
            platform.docker_exec('pip freeze', host),
            platform.get_data('/usr/share/monitor_kraken/requirements.txt', host)
        ) == known_missing


@skipifdev
def test_update_eng_instance_conf_duplicated(duplicated_undeployed):
    platform, fabric = duplicated_undeployed
    # prepare required folder before test
    platform.docker_exec("mkdir -p /srv/kraken")
    fabric.execute('update_eng_instance_conf', 'us-wa')
    assert platform.path_exists('/srv/kraken/us-wa/kraken.ini')
    assert platform.path_exists('/etc/init.d/kraken_us-wa')


@skipifdev
def test_update_eng_instance_conf_distributed(distributed_undeployed):
    platform, fabric = distributed_undeployed
    # prepare required folder before test
    platform.docker_exec("mkdir -p /srv/kraken")
    fabric.execute('update_eng_instance_conf', 'us-wa')
    fabric.execute('update_eng_instance_conf', 'fr-cen')
    assert platform.path_exists('/srv/kraken/us-wa/kraken.ini', 'host1')
    assert platform.path_exists('/etc/init.d//kraken_us-wa', 'host1')
    assert platform.path_exists('/srv/kraken/us-wa/kraken.ini', 'host2', negate=True)
    assert platform.path_exists('/etc/init.d//kraken_us-wa', 'host2', negate=True)
    assert platform.path_exists('/srv/kraken/fr-cen/kraken.ini', 'host2')
    assert platform.path_exists('/etc/init.d/kraken_fr-cen', 'host2')
    assert platform.path_exists('/srv/kraken/fr-cen/kraken.ini', 'host1', negate=True)
    assert platform.path_exists('/etc/init.d/kraken_fr-cen', 'host1', negate=True)
