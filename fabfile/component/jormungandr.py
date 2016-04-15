# coding=utf-8

# Copyright (c) 2001-2015, Canal TP and/or its affiliates. All rights reserved.
#
# This file is part of fabric_navitia, the provisioning and deployment tool
#     of Navitia, the software to build cool stuff with public transport.
#
# Hope you'll enjoy and contribute to this project,
#     powered by Canal TP (www.canaltp.fr).
# Help us simplify mobility and open public transport:
#     a non ending quest to the responsive locomotion way of traveling!
#
# LICENCE: This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
# Stay tuned using
# twitter @navitia
# IRC #navitia on freenode
# https://groups.google.com/d/forum/navitia
# www.navitia.io

import StringIO
import ConfigParser
from io import BytesIO
import json
import fabtools
import requests
from requests.auth import HTTPBasicAuth
from requests.exceptions import ConnectionError
from simplejson.scanner import JSONDecodeError
from time import sleep
from urllib2 import HTTPError

from fabric.colors import red, green, blue, yellow
from fabric.context_managers import settings
from fabric.contrib.files import exists
from fabric.decorators import roles
from fabric.operations import run, get
from fabric.api import execute, task, env, sudo
from fabtools import require, python

from fabfile.component import load_balancer
from fabfile.utils import (_install_packages, _upload_template, get_real_instance,
                           start_or_stop_with_delay, get_bool_from_cli, get_host_addr, show_version)


@task
@roles('ws')
def update_jormungandr_conf():
    """
    update the jormungandr configuration
    """
    require.files.directories([env.jormungandr_base_dir, env.jormungandr_instances_dir, env.jormungandr_log_dir],
                              owner=env.KRAKEN_USER, group=env.KRAKEN_USER, use_sudo=True)

    _upload_template('jormungandr/jormungandr.wsgi.jinja', env.jormungandr_wsgi_file,
                     context={
                         'env': env
                     })
    _upload_template('jormungandr/settings.py.jinja', env.jormungandr_settings_file,
                     context={'env': env})


@task
@roles('ws')
def setup_jormungandr():
    require.users.user('www-data')

    execute(update_jormungandr_conf)

    if env.setup_apache:
        sudo('sudo a2enmod rewrite')
        _upload_template('jormungandr/jormungandr_apache_config.jinja', env.jormungandr_apache_config_file,
                     context={'env': env}, backup=False)

    execute(start_jormungandr_all)

@task
@roles('ws')
#@runs_once
def upgrade_ws_packages():
    packages = [
        'apache2',
        'libapache2-mod-wsgi',
        'logrotate',
        'redis-server',
        'python2.7',
        'git',
        'gcc',
        'python-dev',
        'protobuf-compiler'
    ]
    if env.distrib in ('ubuntu14.04', 'debian8'):
        packages.append('libzmq3-dev')
    elif env.distrib == 'debian7':
        packages.append('libzmq-dev')

    require.deb.packages(packages)
    package_filter_list = ['navitia-jormungandr*deb',
                           'navitia-common*deb']
    _install_packages(package_filter_list)
    if not python.is_pip_installed():
        python.install_pip()

    #we want the version of the system for these packages
    run('''sed -e "/protobuf/d" -e "/psycopg2/d"  /usr/share/jormungandr/requirements.txt > /tmp/jormungandr_requirements.txt''')
    run('git config --global url."https://".insteadOf git://')
    require.python.install_requirements('/tmp/jormungandr_requirements.txt',
            use_sudo=True,
            exists_action='w',
            upgrade=True)


@task
def reload_jormun_safe(server, safe=True):
    """ Reload jormungandr on a specific server,
        in a safe way if load balancers are available
    """
    safe = get_bool_from_cli(safe)
    with settings(host_string=server):
        if env.use_load_balancer and safe:
            load_balancer.disable_node(server)
        sudo("service apache2 reload")
        sleep(1)
        if env.use_load_balancer and safe:
            load_balancer.enable_node(server)

@task
def reload_jormun_safe_all(safe=True, reverse=False):
    """ Reload jormungandr on all servers,
        in a safe way if load balancers are available
    """
    safe = get_bool_from_cli(safe)
    for server in (env.roledefs['ws'][::-1] if reverse else env.roledefs['ws']):
        execute(reload_jormun_safe, server, safe)

@task
def start_jormungandr_all():
    """ Start jormungadr on all servers """
    start_services()
    for server in env.roledefs['ws']:
        execute(reload_jormun_safe, server, False)

@task
@roles('ws')
def start_services():
    start_or_stop_with_delay('apache2', env.APACHE_START_DELAY * 1000, 500, only_once=env.APACHE_START_ONLY_ONCE)

@task
def check_kraken_jormun_after_deploy(show=False):
    headers = {'Host': env.jormungandr_url}

    request_str = 'http://{}{}/v1/status'.format(env.jormungandr_url, env.jormungandr_url_prefix)
    print("request_str: {}".format(request_str))

    try:
        response = requests.get(request_str, headers=headers, auth=HTTPBasicAuth(env.token, ''))
        if response.status_code != 200:
            print(red("Request not successful : {}".format(str(response))))
            return
    except (ConnectionError, HTTPError) as e:
        print(red("HTTP Error %s: %s" % (e.code, e.readlines()[0])))
        return
    except Exception as e:
        print(red("Error when connecting to %s: %s" % (env.jormungandr_url, e)))
        return

    try:
        result = response.json()
    except JSONDecodeError:
        print(red("cannot read json response : {}".format(response.text)))
        return

    candidate_kraken_version = "v" + show_version(action='get')[1]
    warn_dict = dict()
    warn_dict['jormungandr'] = result['jormungandr_version'] if candidate_kraken_version != result['jormungandr_version'] else None
    warn_dict['kraken'] = warn_list = list()

    for item in result['regions']:
        if item['region_id'] not in env.instances:
            continue
        if item['status'] == "dead":
            warn_list.append(dict(status='dead', region_id=item['region_id'], kraken_version=None))
        elif item['kraken_version'] != candidate_kraken_version:
            warn_list.append(dict(status=item['status'], region_id=item['region_id'], kraken_version=item['kraken_version']))
        elif item['status'] == "no_data":
            warn_list.append(dict(status='no_data', region_id=item['region_id'], kraken_version=candidate_kraken_version))

    if show:
        if warn_dict['jormungandr']:
            print(yellow("Jormungandr version={}".format(warn_dict['jormungandr'])))
        for item in warn_list:
            print(yellow("status={status} | region_id={region_id} | kraken_version={kraken_version}".format(**item)))

    return warn_dict


@task
def test_jormungandr(server, instance=None, fail_if_error=True):
    """
    Test jormungandr globally (/v1/coverage) or a given instance

    Note: we don't launch that with a role because we want to test the access from the outside of the server
    """
    headers = {'Host': env.jormungandr_url}

    if instance:
        request_str = 'http://{s}{p}/v1/coverage/{i}/status'.format(s=server, p=env.jormungandr_url_prefix, i=instance)
    else:
        request_str = 'http://{}{}/v1/coverage'.format(server, env.jormungandr_url_prefix)
    print request_str

    try:
        response = requests.get(request_str, headers=headers, auth=HTTPBasicAuth(env.token, ''))
    except (ConnectionError, HTTPError) as e:
        if fail_if_error:
            print(red("HTTP Error %s: %s" % (e.code, e.readlines()[0])))
            exit(1)
        else:
            print(yellow("WARNING: {instance} is running but "
                "problem found: {error} (maybe no data ?)"
                .format(instance=instance, error=e)))
            exit(0)
    except Exception as e:
        print(red("Error when connecting to %s: %s" % (env.jormungandr_url, e)))
        exit(1)

    try:
        result = response.json()
    except JSONDecodeError:
        print(red("cannot read json response : {}".format(response.text)))
        exit(1)

    # if result contain just a message, this indicate a problem
    if 'message' in result:
        print(fail_if_error)
        print(type(fail_if_error))
        if fail_if_error is True:
            print(red("CRITICAL: Problem on result: '{}'".format(result)))
            exit(1)
        print(yellow("WARNING: Problem on result: '{}'".format(result)))
        return False

    if instance:
        print("%s" % result['status'])
        kraken_version = result['status']['kraken_version']
        if kraken_version != env.version:
            #TODO change this version number handling, it should be automatic and not manually set in env.version
            print(yellow("WARNING: Version of kraken (%s) is not the expected %s" %
                 (kraken_version, env.version)))
        else:
            print(green("OK: Version is %s" % kraken_version))
    # just check that there is one instance running
    else:
        regions = result['regions']

        active_instance = [i for i in env.instances.keys() if i not in env.excluded_instances]
        if len(regions) != len(active_instance):
            print red("there is not the right number of instances, "
                      "we should have {ref} but we got {real} instances".
                      format(ref=len(active_instance), real=len(regions)))
            print red('instances in diff: {}'.format(
                set(active_instance).symmetric_difference(set([r['id'] for r in regions]))))
            if fail_if_error:
                exit(1)
            return False
        else:
            #we check that at least one is ok
            statuses = [(r['id'], r['status']) for r in regions]

            if all(map(lambda p: p[1] == 'running', statuses)):
                print green('all instances are ok, everything is fine')
                return True

            print blue('running instances: {}'.format([r[0] for r in statuses if r[1] == 'running']))
            print red('KO instances: {}'.format([r for r in statuses if r[1] != 'running']))

            if fail_if_error:
                exit(1)
            return False

    return True


@task
@roles('ws')
def deploy_jormungandr_instance_conf(instance):
    instance = get_real_instance(instance)
    config = {'key': instance.name, 'zmq_socket': instance.jormungandr_zmq_socket_for_instance}
    config['realtime_proxies'] = instance.realtime_proxies

    _upload_template("jormungandr/instance.json.jinja",
                     instance.jormungandr_config_file,
                     context={
                         'json': json.dumps(config, indent=4)
                     },
                     use_sudo=True
    )

    # the old configuration file were .ini, now it's json, we need to clean up
    if fabtools.files.is_file(instance.jormungandr_old_ini_config_file):
        fabtools.files.remove(instance.jormungandr_old_ini_config_file)


@task
@roles('ws')
def remove_jormungandr_instance(instance):
    """Remove a jormungandr instance entirely
        * Remove json file which declare the instance
        * Reload apache
    """
    run("rm --force %s/%s.json" % (env.jormungandr_instances_dir, instance))

    # TODO refactor this (seems NxN) !
    for server in env.roledefs['ws']:
        print("→ server: {}".format(server))
        execute(reload_jormun_safe, server)


@task
def deploy_jormungandr_all_instances_conf():
    for instance in env.instances.itervalues():
        execute(deploy_jormungandr_instance_conf, instance)
