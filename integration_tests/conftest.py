# encoding: utf-8

import time
import pytest

from docker import PlatformManager, DeployedPlatformManager
from fabric_integration import FabricManager


def pytest_addoption(parser):
    parser.addoption('--dev', action='store_true',
                     help="run only non decorated tests (default: run all tests")
    parser.addoption('--reset', action='store_true',
                     help="force reset image, ie force a full navitia redeploy "
                          "(default: reuse existing image")
    parser.addoption('--distri', action='store', default='debian8',
                     help="select a linux distribution (default debian8)")


# ===================     UNDEPLOYED PLATFORMS FIXTURES     =======================

def setup_platform(platform, distri):
    print()
    # build an image ready for Navitia2, then run it
    platform.setup('rm_container')
    # then set up the fabric platform
    return platform, FabricManager(platform).set_platform(distrib=distri)


@pytest.yield_fixture(scope='function')
def single_undeployed():
    distri = pytest.config.getoption('--distri')
    platform = PlatformManager('single', {'host': distri})
    platform, fabric = setup_platform(platform, distri)
    yield platform, fabric
    platform.reset('rm_container')


@pytest.yield_fixture(scope='function')
def distributed_undeployed():
    distri = pytest.config.getoption('--distri')
    platform = PlatformManager('distributed', {'host1': distri, 'host2': distri})
    platform, fabric = setup_platform(platform, distri)
    yield platform, fabric
    platform.reset('rm_container')


@pytest.yield_fixture(scope='function')
def duplicated_undeployed():
    distri = pytest.config.getoption('--distri')
    platform = PlatformManager('duplicated', {'host1': distri, 'host2': distri})
    platform, fabric = setup_platform(platform, distri)
    yield platform, fabric
    platform.reset('rm_container')


# ===================     DEPLOYED PLATFORMS FIXTURES     =======================

def setup_platform_deployed(platform, distri):
    print()
    fabric = FabricManager(platform)
    deployed_platform = DeployedPlatformManager(platform, distri).setup(pytest.config.getoption('--reset') and 'uproot')
    return deployed_platform, fabric


@pytest.yield_fixture(scope='function')
def single():
    distri = pytest.config.getoption('--distri')
    platform = PlatformManager('single', {'host': distri})
    deployed_platform, fabric = setup_platform_deployed(platform, distri)
    time.sleep(1)
    deployed_platform.start_services('tyr_worker', 'tyr_beat', 'default', wait='/srv/kraken')
    yield deployed_platform, fabric
    deployed_platform.reset('rm_container')


@pytest.yield_fixture(scope='function')
def distributed():
    distri = pytest.config.getoption('--distri')
    platform = PlatformManager('distributed', {'host1': distri, 'host2': distri})
    deployed_platform, fabric = setup_platform_deployed(platform, distri)
    time.sleep(1)
    deployed_platform.start_services(
        'tyr_worker',
        host1=('tyr_beat', 'kraken_fr-nw', 'kraken_us-wa', 'kraken_fr-npdc'),
        host2=('kraken_fr-ne-amiens', 'kraken_fr-idf', 'kraken_fr-cen'),
        wait='/srv/kraken'
    )
    yield deployed_platform, fabric
    deployed_platform.reset('rm_container')


@pytest.yield_fixture(scope='function')
def duplicated():
    distri = pytest.config.getoption('--distri')
    platform = PlatformManager('duplicated', {'host1': distri, 'host2': distri})
    deployed_platform, fabric = setup_platform_deployed(platform, distri)
    time.sleep(1)
    deployed_platform.start_services(
        'tyr_worker',
        'kraken_fr-nw', 'kraken_us-wa', 'kraken_fr-npdc', 'kraken_fr-ne-amiens', 'kraken_fr-idf', 'kraken_fr-cen',
        host1=('tyr_beat',),
        wait='/srv/kraken'
    )
    yield deployed_platform, fabric
    deployed_platform.reset('rm_container')
