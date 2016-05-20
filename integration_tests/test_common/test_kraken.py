# encoding: utf-8

import time

from ..utils import extract_column, get_running_krakens


def _start_and_check_krakens(platform, map):
    platform, fabric = platform
    # make sure that krakens are started
    fabric.execute('require_all_krakens_started')
    time.sleep(1)
    # check that krakens are running
    for host, kraks in map.iteritems():
        assert set(get_running_krakens(platform, host)) == kraks


def _test_stop_restart_kraken(platform, map_start, map_stop, stop_pat, start_pat):
    _start_and_check_krakens(platform, map_start)
    platform, fabric = platform

    # stop some krakens and check them
    if stop_pat[1]:
        for krak in stop_pat[1]:
            fabric.execute(stop_pat[0], krak)
    else:
        fabric.execute(stop_pat[0])
    time.sleep(1)
    for host, kraks in map_stop.iteritems():
        assert set(get_running_krakens(platform, host)) == kraks

    # restart krakens and check them
    if start_pat[1]:
        for krak in start_pat[1]:
            fabric.execute(start_pat[0], krak, **(start_pat[2]))
    else:
        fabric.execute(start_pat[0], **(start_pat[2]))
    time.sleep(1)
    for host, kraks in map_start.iteritems():
        assert set(get_running_krakens(platform, host)) == kraks


def _test_stop_start_apache(platform, hosts):
    platform, fabric = platform
    # make sure that krakens are started
    fabric.execute('require_all_krakens_started')

    for host in hosts:
        assert 'apache2' in extract_column(platform.docker_exec('ps -A', host), -1, 1)
    platform.ssh('service apache2 stop')
    time.sleep(2)
    for host in hosts:
        assert 'apache2' not in extract_column(platform.docker_exec('ps -A', host), -1, 1)
    fabric.execute('require_monitor_kraken_started')
    time.sleep(2)
    for host in hosts:
        assert 'apache2' in extract_column(platform.docker_exec('ps -A', host), -1, 1)


def _test_test_kraken_nowait_nofail(platform, capsys, map, ret_val):
    platform, fabric = platform

    # test monitor-kraken request
    for host, kraks in map.iteritems():
        krak = tuple(kraks)[0]
        assert fabric.execute('test_kraken', krak, fail_if_error=False).values()[0] is ret_val
        out, err = capsys.readouterr()
        assert 'http://{}:80/monitor-kraken/?instance={}'.format(platform.get_hosts()[host], krak) in out
        assert "OK: instance %s has correct values: {u'status': u'running', u'is_realtime_loaded': False, " \
               "u'start_production_date': u'', u'last_load': u'not-a-date-time', u'end_production_date': u'', " \
               "u'loaded': False, u'publication_date': u'', u'last_load_status': True, " \
               "u'is_connected_to_rabbitmq': True}" % krak in out
