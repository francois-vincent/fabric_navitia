# encoding: utf-8

import os.path
import pytest

from ..docker import PlatformManager, container_stop
from ..docker import ROOTDIR as DOCKER_ROOTDIR
from ..fabric_integration import FabricManager
from ..utils import cd, extract_column, filter_column, command, Command
from ..test_common import skipifdev

ROOTDIR = os.path.dirname(os.path.abspath(__file__))


def test_classes():
    # Create a platform with associated fabric manager
    platform = PlatformManager('navitia', {'h1': 'debian8', 'h2': 'debian8'},
                               (('h1', '--param 0'),))
    FabricManager(platform)

    # Check that platform is initialized
    assert platform.images_rootdir == DOCKER_ROOTDIR
    assert platform.platform_name == 'navitia'
    assert platform.images == {'h1': 'debian8', 'h2': 'debian8'}
    assert platform.parameters == {'h1': '--param 0'}
    assert platform.containers == {'h1': 'debian8-navitia-h1', 'h2': 'debian8-navitia-h2'}
    assert set(platform.containers_names) == {'debian8-navitia-h1', 'debian8-navitia-h2'}
    assert platform.images_names == {'debian8'}
    assert set(platform.hosts_ips) == {'h1', 'h2'}

    # check that fabric manager is initialized
    assert platform.managers['fabric'].platform == platform


def test_extract_column():
    assert extract_column('', 0, 0) == []
    text = """a1 a2 a3 a4
       b1 b2 b3 b4
       c1 c2 c3     c4
       d1  d2 d3  d4
    """
    assert extract_column(text, 0, 0) == ['a1', 'b1', 'c1', 'd1']
    assert extract_column(text, -1, 0) == ['a4', 'b4', 'c4', 'd4']
    assert extract_column(text, 0, 1) == ['b1', 'c1', 'd1']
    assert extract_column(text, 1, 1) == ['b2', 'c2', 'd2']


def test_filter_column():
    with pytest.raises(TypeError):
        filter_column('', 0)
    with pytest.raises(ValueError):
        filter_column('', 0, toto='')
    text = """toto titi bob
       tototo xtitito blob
       aaaa bbbb job
    """
    assert filter_column(text, 0, eq='toto') == ['toto titi bob']
    assert filter_column(text, 0, startswith='toto') == ['toto titi bob', 'tototo xtitito blob']
    assert filter_column(text, 1, contains='titi') == ['toto titi bob', 'tototo xtitito blob']
    assert filter_column(text, 2, endswith='ob') == ['toto titi bob', 'tototo xtitito blob', 'aaaa bbbb job']


@skipifdev
def test_command(capsys):
    # you can't retrieve stdout nor stdin
    with cd(ROOTDIR):
        assert command('pwd') == 0
    assert command('fancycommand') > 0
    out, err = capsys.readouterr()
    assert (out, err) == ('', '')


@skipifdev
def test_Command(capsys):
    with cd(ROOTDIR):
        com = Command('pwd')
    assert com.returncode == 0
    assert com.stdout.strip() == ROOTDIR
    assert com.stderr == ''
    with cd(ROOTDIR):
        com = Command('fancycommand')
    assert com.returncode > 0
    assert com.stdout == ''
    assert com.stderr.strip() == '/bin/sh: 1: fancycommand: not found'
    out, err = capsys.readouterr()
    assert (out, err) == ('', '')


@skipifdev
def test_build_delete_images():
    platform = PlatformManager('test', {'host': 'testimage'})
    platform.build_images(reset='uproot')
    assert platform.get_real_images() == ['testimage']
    platform.reset('rm_image')
    assert platform.get_real_images() == []


@skipifdev
def test_run_stop_delete_containers():
    platform = PlatformManager('test', {'host': 'testimage'}).build_images()
    platform.run_containers(reset='rm_container')
    assert platform.get_real_containers() == ['testimage-test-host']
    platform.containers_stop()
    assert platform.get_real_containers() == []
    assert platform.get_real_containers(True) == ['testimage-test-host']
    platform.containers_delete()
    assert platform.get_real_containers(True) == []


@skipifdev
def test_get_hosts():
    platform = PlatformManager('test', {'host1': 'testimage', 'host2': 'testimage'}).build_images().run_containers()
    assert set(platform.get_real_containers()) == {'testimage-test-host1', 'testimage-test-host2'}
    hosts = platform.get_hosts()
    assert set(hosts.keys()) == {'host1', 'host2'}
    assert '172.17.' in hosts['host1']
    assert '172.17.' in hosts['host2']
    container_stop('testimage-test-host2')
    hosts = platform.get_hosts()
    assert set(hosts.keys()) == {'host1', 'host2'}
    assert '172.17.' in hosts['host1']
    assert '' == hosts['host2']
    try:
        platform.get_hosts(raises=True)
        assert 0, "Should raise a RuntimeError"
    except RuntimeError as e:
        assert e.args == ('Expecting 2 running containers, found 1', )
    except Exception as e:
        assert 0, "Should raise a RuntimeError, raised {}".format(e)


@skipifdev
def test_ssh():
    platform = PlatformManager('test', {'host1': 'testimage', 'host2': 'testimage'}).build_images().run_containers()
    assert platform.ssh('pwd') == {'host1': '/root', 'host2': '/root'}
    assert platform.ssh('pwd', host='host1') == '/root'


@skipifdev
def test_docker_exec():
    platform = PlatformManager('test', {'host1': 'testimage', 'host2': 'testimage'}).build_images().run_containers()
    assert platform.docker_exec('pwd') == {'host1': '/', 'host2': '/'}
    assert platform.docker_exec('pwd', host='host1') == '/'


@skipifdev
def test_ssh_put_file_exists():
    platform = PlatformManager('test', {'host1': 'testimage', 'host2': 'testimage'}).build_images().run_containers()
    platform.ssh('mkdir /root/testdir')
    platform.scp(os.path.join(ROOTDIR, 'dummy.txt'), '/root/testdir')
    assert platform.ssh('cat /root/testdir/dummy.txt') == {'host1': 'hello world', 'host2': 'hello world'}
    assert platform.path_exists('/root/testdir/dummy.txt')
    platform.ssh('rm -f /root/testdir/dummy.txt', 'host1')
    assert platform.path_exists('/root/testdir/dummy.txt', 'host2')
    assert not platform.path_exists('/root/testdir/dummy.txt', 'host1')
    platform.ssh('rm -rf /root/testdir')


@skipifdev
def test_put_file_exists():
    platform = PlatformManager('test', {'host1': 'testimage', 'host2': 'testimage'}).build_images().run_containers()
    platform.docker_exec('mkdir /root/testdir')
    platform.scp(os.path.join(ROOTDIR, 'dummy.txt'), '/root/testdir')
    assert platform.docker_exec('cat /root/testdir/dummy.txt') == {'host1': 'hello world', 'host2': 'hello world'}
    assert platform.path_exists('/root/testdir/dummy.txt')
    platform.docker_exec('rm -f /root/testdir/dummy.txt', 'host1')
    assert platform.path_exists('/root/testdir/dummy.txt', 'host2')
    assert not platform.path_exists('/root/testdir/dummy.txt', 'host1')
    platform.docker_exec('rm -rf /root/testdir')


@skipifdev
def test_put_get_data():
    platform = PlatformManager('test', {'host1': 'testimage', 'host2': 'testimage'}).build_images().run_containers()
    platform.docker_exec('mkdir /root/testdir')
    platform.put_data('fluctuat nec mergitur', '/root/testdir/bob.txt')
    assert platform.get_data('/root/testdir/bob.txt') == {'host1': 'fluctuat nec mergitur', 'host2': 'fluctuat nec mergitur'}
    platform.docker_exec('rm -rf /root/testdir')
