# encoding: utf-8

import os.path
import time

from fabric import api

from ..docker import get_container_ip, PlatformManager
from ..fabric_integration import FabricManager
from ..utils import extract_column

ROOTDIR = os.path.dirname(os.path.abspath(__file__))


def test_single():
    # ---- setup
    # Create a platform with associated fabric manager
    platform = PlatformManager('single', {'host': 'debian8'})
    fabric = FabricManager(platform)

    # build a debian8 image ready for Navitia2, then run it
    platform.setup()
    time.sleep(1)
    # then set up the fabric platform
    fabric.set_platform()
    host_ip = get_container_ip('debian8-single-host')

    # ---- selftests
    # Check there's a debian8 image build
    assert platform.get_real_images() == platform.images.values()
    # check that container is started
    assert platform.get_real_containers() == ['debian8-single-host']
    assert host_ip
    # check some platform instantiations in fabric
    assert api.env.name == 'single'
    assert api.env.roledefs['tyr'] == ['root@' + host_ip]
    # Check I can ssh to it
    assert platform.ssh('pwd') == {'host': '/root'}
    # Check expected processes are running in it
    assert {'ps', 'sshd', 'supervisord', 'beam.smp', 'inet_gethost', 'su', 'apache2',
            'epmd', 'rabbitmq-server', 'sh', 'redis-server', 'postgres'}.\
        issubset(set(extract_column(platform.ssh('ps -A', 'host'), -1, 1)))
    # check scp file transfer
    platform.ssh('mkdir /root/testdir')
    platform.scp(os.path.join(ROOTDIR, 'dummy.txt'), '/root/testdir')
    assert platform.ssh('cat /root/testdir/dummy.txt', 'host') == 'hello world'
    platform.ssh('rm -rf /root/testdir')


def test_dual():
    # ---- setup
    # Create a platform with associated fabric manager
    platform = PlatformManager('distributed', {'host1': 'debian8', 'host2': 'debian8light'})
    fabric = FabricManager(platform)

    # build a debian8 image ready for Navitia2, then run it
    platform.setup()
    time.sleep(1)
    # then set up the fabric platform
    fabric.set_platform()
    host1_ip = get_container_ip('debian8-distributed-host1')
    host2_ip = get_container_ip('debian8light-distributed-host2')

    # ---- selftests
    # Check the images are there
    assert set(platform.get_real_images()) == {'debian8', 'debian8light'}
    # check that containers are started
    assert set(platform.get_real_containers()) == {'debian8-distributed-host1', 'debian8light-distributed-host2'}
    assert host1_ip
    assert host2_ip
    # check some platform instantiations in fabric
    assert api.env.name == 'distributed'
    assert api.env.roledefs['eng'] == ['root@' + host1_ip, 'root@' + host2_ip]
    # Check I can ssh to it
    assert platform.ssh('pwd') == {'host1': '/root', 'host2': '/root'}
    # Check expected processes are running in it
    assert {'ps', 'sshd', 'supervisord', 'beam.smp', 'inet_gethost', 'su', 'apache2',
            'epmd', 'rabbitmq-server', 'sh', 'redis-server', 'postgres'}.\
        issubset(set(extract_column(platform.ssh('ps -A', 'host1'), -1, 1)))
    assert {'ps', 'sshd', 'supervisord', 'apache2'}.\
        issubset(set(extract_column(platform.ssh('ps -A', 'host2'), -1, 1)))
    # check scp file transfer
    platform.ssh('mkdir /root/testdir')
    platform.scp(os.path.join(ROOTDIR, 'dummy.txt'), '/root/testdir')
    assert platform.ssh('cat /root/testdir/dummy.txt') == {'host1': 'hello world', 'host2': 'hello world'}
    platform.ssh('rm -rf /root/testdir')
