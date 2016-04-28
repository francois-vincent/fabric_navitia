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

from contextlib import contextmanager
from envelopes import Envelope
import functools
from multiprocessing.dummy import Pool as ThreadPool
from fabric.context_managers import settings
import os
import random
from retrying import Retrying, RetryError
import string
import time
import datetime
import semver
from abc import ABCMeta, abstractmethod
import re

import requests
from requests.auth import HTTPBasicAuth

from fabric.colors import green, yellow, red
from fabric.context_managers import cd
from fabric.api import env, task, roles, run, put, sudo, warn_only, execute
from fabric.contrib.files import exists
from fabtools.files import upload_template
from fabtools import require
from fabtools.require.files import temporary_directory


# thanks
# http://freepythontips.wordpress.com/2013/07/28/generating-a-random-string/
def _random_generator(size=8, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for x in range(size))


def _install_packages(package_filter):

    # if we don't want to use a repository but just dpkg --install packages
    if env.manual_package_deploy:
        #it is not optimal, each package will be potentially copied several times, we'll have to improve that
        with temporary_directory() as tmp_dir:
            for package in package_filter:
                if env.debian_packages_path:
                    package = "{path}/{package}".format(path=env.debian_packages_path, package=package)
                put(package, tmp_dir)
            with cd(tmp_dir):
                with warn_only():#@TODO: catch only on error
                    sudo('dpkg --install {}'.format(' '.join(package_filter)))
                #Install dependencies
                sudo('apt-get -f --yes install')
    # else suppose that the machine is configured to use a remote repository
    else:
        # don't want filename package, just the name
        # --quiet to pretty print progress in fabric
        sudo('apt-get -f --quiet update && apt-get --yes install {}'
        .format(' '.join(package_filter).replace('*deb', '')))


@task
@roles('tyr', 'eng', 'ws')
def stop_puppet():
    run("service puppet stop")


@task
@roles('tyr', 'eng', 'ws')
def start_puppet():
    run("service puppet stop")


@task
@roles('tyr_master')
def compute_instance_status(instance):
    """
    check if it is the first deployement of the instance

    the check that we check the existence of the base dir
    """
    print instance.base_ed_dir
    instance.first_deploy = not exists(instance.base_ed_dir)
    print "instance {i} is {s}".format(i=instance.name, s='new' if instance.first_deploy else 'not new')


def require_directory(dirs, is_on_nfs4=False, **kwargs):
    """
    create the directory if it does not exists

    if the directory is on nfs4 (and the environement supports it) we do not chown the directory,
    access right are handled externaly via acl
    """
    print "creating directory {}".format(dirs)
    if env.use_nfs4 and is_on_nfs4:
        print('removing chown')
        if 'owner' in kwargs:
            del kwargs['owner']
        if 'group' in kwargs:
            del kwargs['group']
    require.files.directory(dirs, **kwargs)


def require_directories(dirs, is_on_nfs4=False, **kwargs):
    """
    create the directories if it does not exists

    if the directory is on nfs4 (and the environement supports it) we do not chown the directory,
    access right are handled externaly via acl
    """
    if env.use_nfs4 and is_on_nfs4:
        if 'owner' in kwargs:
            del kwargs['owner']
        if 'group' in kwargs:
            del kwargs['group']
    require.files.directories(dirs, **kwargs)

    
def _upload_template(filename, destination, context=None, chown=True, user='www-data', **kwargs):
    kwargs['use_jinja'] = True
    kwargs['template_dir'] = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                          os.path.pardir, 'templates')
    kwargs['context'] = context
    kwargs['mkdir'] = False
    kwargs['chown'] = chown
    kwargs['user'] = user
    kwargs['use_sudo'] = True
    kwargs['backup'] = env.backup_conf_files
    upload_template(filename, destination, **kwargs)


def get_psql_version():
    version_lines = run('psql --version')
    v_line = version_lines.split('\n')[0]
    return v_line.split(" ")[-1].split(".")


def get_host_addr(host):
    """
    get the address of the server from the ssh connection string

    dumb split on the @
    eq root@toto.fr returns toto.fr
    """
    return host.split('@')[-1]


class Parallel:
    """
    run job in multi thread

    syntaxic sugar around multiprocessing.dummy

    use it as RAII eg:
    with Parallel(4) as p:
        p.map(my_function, my_param_array)
    """
    def __init__(self, nb_thread):
        self.pool = ThreadPool(nb_thread)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print("leaving parallele for")
        self.pool.close()
        self.pool.join()

    def map(self, func, param):
        self.pool.map(func, param)


def run_once_per_host(func):
    """
    Don't invoke `func` more than once for host and arguments.
    """
    func.past_results = {}
    @functools.wraps(func)
    def decorated(*args, **kwargs):
        key = (env.host_string, args, tuple(kwargs.items()))
        if key not in func.past_results:
            func.past_results[key] = func(*args, **kwargs)
        return func.past_results[key]
    return decorated


@contextmanager
def time_that(message):
    """
    measure time of all work done under the 'with'

    print the message with the {elapsed} variable formated with the time
    """
    start_time = time.time()
    yield
    elapsed_time = time.time() - start_time
    print(message.format(elapsed=datetime.timedelta(seconds=elapsed_time)))


# Retrieve Instance from string/unicode if needed
def get_real_instance(instance):
    """ if 'instance' is a string get the corresponding instance, else return the instance """
    if isinstance(instance, basestring):
        return env.instances[instance]
    return instance

host_app_mapping = dict(
    tyr='navitia-tyr',
    eng='navitia-kraken',
    ws='navitia-jormungandr'
)

@run_once_per_host
@task
def apt_get_update():
    sudo('apt-get update')


@task
def get_version(host):
    app_name = host_app_mapping[host]
    with settings(host_string=env.roledefs[host][0]):
        execute(apt_get_update)
        lines = run('apt-cache policy %s' % app_name).split('\n')
        try:
            installed = lines[1].strip().split()[-1]
            candidate = lines[2].strip().split()[-1]
        except IndexError:
            installed, candidate = None, None
        return installed, candidate

@task
def show_version(action='show', host='eng'):
    """
    prints, gets or checks versions (installed and candidate) from navitia-kraken/navitia-tyr/navitia-jormungandr package
    show: print versions on stdout
    get: returns tuple (installed, candidate) or (None, None) if navitia-kraken/tyr/jormungandr not installed on target,
         installed and candidate can be tuples if different versions are coexisting
    check: return True if candidate version is different from installed
    """
    versions = execute(get_version, host)
    def summarize(iterable):
        s = tuple(set(iterable))
        if len(s) == 1:
            return s[0]
        return s
    if action == 'show':
        print(green(host_app_mapping[host]))
        for k, v in versions.iteritems():
            print(green("  %s, installed: %s, candidate: %s" % (k, v[0], v[1])))
    elif action == 'get':
        installed = summarize(x[0] for x in versions.itervalues())
        candidate = summarize(x[1] for x in versions.itervalues())
        return installed, candidate
    elif action == 'check':
        if env.manual_package_deploy:
            print(yellow("WARNING Can't check versions of manually installed packages"))
            return True
        installed = summarize(x[0] for x in versions.itervalues())
        candidate = summarize(x[1] for x in versions.itervalues())
        if isinstance(installed, tuple):
            installed = max(installed)
        return semver.compare(candidate, installed) > 0


@task
def update_init(host):
    with settings(host_string=env.roledefs[host][0],
                  warn_only=True):
        if run('which systemd'):
            run('systemctl daemon-reload')
        else:
            print('systemd is not installed')


class send_mail(object):
    """
    Mail sending class.
    Class attributes are default messages and subjects
    These can be overriden with keys in env.emails dict.
    env.emails dict must specify at least 'to' and 'server' keys,
    if not, no email is sent and a warning message is printed.
    """
    start_mail_subject = u"Starting deployment of Navitia 2 v{version} on plateform {target}"
    start_mail_message = u"The deployment of the new version of Navitia 2 is starting on plateform %s" \
                         u"\nYou may be impacted."
    finished_mail_subject = u"End of deployment of Navitia 2 v{version} on plateform {target}"
    finished_mail_message = u"New version of Navitia 2 deployed on %s.\n\o/ thank you for your patience !"
    email_author = (u'Navitia-noreply', u'Navitia Deployment')

    def __init__(self):
        self.mail_load = getattr(env, 'emails', {})
        self.candidate = execute(show_version, action='get').values()[0][1]

    def send_mail(self, message, subject):
        mail = Envelope(
            from_addr=self.mail_load.get('author', self.email_author),
            to_addr=self.mail_load['to'].split(';'),
            subject=subject.format(version=self.candidate, target=env.name.upper()),
            text_body=message % env.name.upper()
        )
        if self.mail_load.get('cc'):
            for cc in self.mail_load['cc'].split(';'):
                mail.add_cc_addr(cc)
        mail.send(self.mail_load['server'])

    def send_start(self, status=None):
        if self.mail_load:
            try:
                end_message = self.mail_load.get('start_mes', self.start_mail_message)
                if status:
                    end_message += status
                self.send_mail(
                    end_message,
                    self.mail_load.get('start_sub', self.start_mail_subject)
                )
            except (KeyError, AttributeError) as e:
                print(yellow("Can't send start email: %r" % e))
        return self

    def send_end(self, status=None):
        if self.mail_load:
            try:
                end_message = self.mail_load.get('end_mes', self.finished_mail_message)
                if status:
                    end_message += status
                self.send_mail(
                    end_message,
                    self.mail_load.get('end_sub', self.finished_mail_subject)
                )
            except (KeyError, AttributeError) as e:
                print(yellow("Can't send finished email: %r" % e))


def get_bool_from_cli(x):
    if isinstance(x, bool):
        return x
    return x != 'False'


def start_or_stop_with_delay(service, delay, wait, start=True, only_once=False, exc_raise=False):
    # TODO refactor to overcome the SSH problem with respect to "service start"
    # see: https://github.com/fabric/fabric/issues/395
    cmd = require.service.started if start else require.service.stopped
    retry_cond = (lambda x: not require.service.is_running(service)) if start \
                 else (lambda x: require.service.is_running(service))
    if only_once:
        cmd(service)
        cmd = lambda x: None
    try:
        Retrying(stop_max_delay=delay, wait_fixed=wait,
                 retry_on_result=retry_cond).call(cmd, service)
    except RetryError as e:
        message = "Service {} {} failed: ".format(service, 'start' if start else 'stop') + repr(e)
        if exc_raise:
            raise RuntimeError(message)
        print(red(message))
        return False
    return True


def show_dead_kraken_status(warn_dict, show=False):
    status = "\n\n---------- Status" \
             "\nThere are {} instances.".format(len(env.instances))

    if warn_dict:
        if warn_dict['jormungandr'] is None and not warn_dict['kraken']:
            status += "\nAll instances are clean and updated!"
        if warn_dict['jormungandr']:
            status += "\nJormungandr version={}".format(warn_dict['jormungandr'])
        if warn_dict['kraken']:
            version_sort = sorted(warn_dict['kraken'], key=lambda i: i.get('kraken_version'), reverse=True)
            for item in version_sort:
                status += "\nKraken {region_id} status={status} version={kraken_version}".format(**item)

    if show:
        print(yellow(status))
    return status


class TimeCollector(object):
    def __init__(self):
        self.start_time = {}
        self.end_time = {}

    def register_start(self, service):
        self.start_time[service] = datetime.datetime.now()

    def register_end(self, service):
        self.end_time[service] = datetime.datetime.now()

    def get_duration(self, service, format=None):
        du = self.end_time[service] - self.start_time[service]
        if format == 'minutes':
            return du.total_seconds()/60
        elif format == 'hours':
            return du.total_seconds()/3600
        else:
            return du


def show_time_deploy(td, show=False):
    time_deploy = ''
    if 'total_deploy' in td.end_time:
        time_deploy += "\nTotal deployment time: {} ({:.2f} hours)".\
            format(td.get_duration('total_deploy'), td.get_duration('total_deploy', format='hours'))
    if 'bina' in td.end_time:
        time_deploy += "\nBinarization time: {} ({:.2f} hours)".\
            format(td.get_duration('bina'), td.get_duration('bina', format='hours'))
    if 'kraken' in td.end_time:
        time_deploy += "\nKraken reload time: {} ({:.2f} minutes)".\
            format(td.get_duration('kraken'), td.get_duration('kraken', format='minutes'))
    if time_deploy:
        time_deploy = "\n\n--------- Time" + time_deploy

    if show and time_deploy:
        print(yellow(time_deploy))

    return time_deploy


class SupervisionHandler(object):
    __metaclass__ = ABCMeta

    @abstractmethod
    def stop_supervision(self, host, service, duration=None):
        """
        stop the supervision for a service of a host
        Optional: definition of a timer
        """
        return

    @abstractmethod
    def start_supervision(self, host, service):
        """
        start or restart the supervision for a service of a host
        """
        return


class NagiosSupervisionHandler(SupervisionHandler):
    def __init__(self, url, user, pwd):
        self.url = url
        self.user = user
        self.pwd = pwd

    def format_host(self, host):
        """the nagio supervisor only wants a short host name"""
        move_host = re.compile(r'@(.*?)\.')
        return move_host.search(host).group(1)

    def stop_supervision(self, host, service, duration):
        if not duration:
            raise ValueError("'duration' attribute must be defined and positive.")

        start_dt = datetime.datetime.now()
        start_str = start_dt.strftime('%d-%m-%Y %H:%M:%S')

        end_dt = start_dt + datetime.timedelta(minutes=duration)
        end_str = end_dt.strftime('%d-%m-%Y %H:%M:%S')

        ctp_host = self.format_host(host)
        message = 'Deployment'

        datas = {'cmd_typ': 56, 'cmd_mod': 2, 'host': ctp_host, 'service': service,
                 'com_author': self.user, 'com_data': message, 'trigger': 0,
                 'start_time': start_str, 'end_time': end_str, 'fixed': 1,
                 'hours': 2, 'minutes': 0, 'btnSubmit': 'Commit'}

        requests.get(self.url, auth=HTTPBasicAuth(self.user, self.pwd), params=datas, verify=False)

    def start_supervision(self, host, service):
        """
        for the moment we don't know how to put back the supervision
        TODO
        """
        pass


def supervision_downtime(step):
    """
    during the deployment, the supervision is stopping for specific services
    """
    if not env.supervision_handler:
        return

    step_data = env.supervision_config[step]
    if step_data['downtime']:
        for host in step_data['hosts']:
            if '{instance}' in step_data['service']:
                for instance in env.instances:
                    service = step_data['service'].format(instance=instance)
                    env.supervision_handler.stop_supervision(host, service, step_data['downtime'])
            else:
                env.supervision_handler.stop_supervision(host, step_data['service'], step_data['downtime'])
