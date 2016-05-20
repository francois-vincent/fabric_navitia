# encoding: utf-8

from clingon import clingon
clingon.DEBUG = True

from ..docker import PlatformManager
from ..fabric_integration import FabricManager


@clingon.clize
def factory(
        distri,
        execute='no',
        host='host',
        reset='rm_container',
        commit=False
):
    platform_obj = PlatformManager('single', {host: distri})
    platform_obj.setup(reset)
    fabric = FabricManager(platform_obj)
    if execute != 'no':
        fabric.set_platform().execute(execute)
        if commit:
            platform_obj.commit_containers()
