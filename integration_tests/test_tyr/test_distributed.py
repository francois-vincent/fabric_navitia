# encoding: utf-8

import time

from ..test_common import skipifdev


@skipifdev
def test_create_remove_tyr_instance(distributed):
    platform, fabric = distributed
    fabric.get_object('instance.add_instance')('toto', 'passwd',
                       zmq_socket_port=30004, zmq_server=fabric.env.host1_ip)
    # postgres is really long to warm up !
    time.sleep(15)

    value, exception, stdout, stderr = fabric.execute_forked('create_tyr_instance', 'toto')
    assert stdout.count("Executing task 'create_tyr_instance'") == 2
    assert stdout.count("Executing task 'create_instance_db'") == 2
    assert platform.path_exists('/srv/ed/data/toto')
    assert platform.path_exists('/srv/ed/data/toto/backup')
    assert platform.path_exists('/srv/ed/toto')
    assert platform.path_exists('/var/log/tyr/toto.log')
    assert platform.path_exists('/etc/tyr.d/toto.ini')
    assert platform.path_exists('/srv/ed/toto/alembic.ini')
    assert platform.path_exists('/srv/ed/toto/settings.sh')

    time.sleep(2)
    with fabric.set_call_tracker('component.tyr.restart_tyr_worker',
                                 'component.tyr.restart_tyr_beat') as data:
        value, exception, stdout, stderr = fabric.execute_forked('remove_tyr_instance', 'toto', purge_logs=True)
    assert stdout.count("Executing task 'remove_tyr_instance'") == 2
    assert platform.path_exists('/etc/tyr.d/toto.ini', negate=True)
    assert platform.path_exists('/var/log/tyr/toto.log', negate=True)
    # restart_tyr_worker is called twice (good)
    assert len(data()['restart_tyr_worker']) == 2
    # restart_tyr_beat is called twice (not so good)
    assert len(data()['restart_tyr_beat']) == 2
