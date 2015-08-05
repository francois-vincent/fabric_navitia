# encoding: utf-8
import StringIO
import ConfigParser
from io import BytesIO
from retrying import Retrying
import simplejson as json
from urllib2 import Request, urlopen, HTTPError

from fabfile.utils import get_bool_from_cli
from fabric.colors import blue, red, green, yellow
from fabric.context_managers import settings
from fabric.contrib.files import exists, sed
from fabric.decorators import roles, serial
from fabric.operations import run, get
from fabric.api import task, env, sudo
from fabtools import require, service, files

from fabfile.utils import (_install_packages, get_real_instance, _upload_template,
                           start_or_stop_with_delay, get_host_addr)


@task
@roles('eng')
def setup_kraken():
    require.users.user('www-data')
    require.files.directories([env.kraken_basedir, env.kraken_log_basedir,
        env.kraken_monitor_basedir], owner=env.KRAKEN_USER, group=env.KRAKEN_USER,
        use_sudo=True)
    update_monitor_configuration()
    if env.setup_apache:
        _upload_template('kraken/monitor_apache_config.jinja', env.kraken_monitor_apache_config_file,
                     context={'env': env}, backup=False)
    require.service.started('apache2')

@task
@roles('eng')
def upgrade_engine_packages():
    packages = ['logrotate', 'python2.7', 'rabbitmq-server', 'gcc',
            'python-dev']
    if env.distrib in ('ubuntu14.04', 'debian8'):
        packages.append('libzmq3-dev')
    elif env.distrib == 'debian7':
        packages.append('libzmq-dev')
    require.deb.packages(packages, update=True, options=['-f'])
    package_filter_list = ['navitia-kraken*deb',
                           'navitia-kraken-dbg*deb']
    _install_packages(package_filter_list)


@task
@roles('eng')
def upgrade_monitor_kraken_packages():
    package_filter_list = ['navitia-monitor-kraken*deb']
    _install_packages(package_filter_list)
    require.python.install_pip()
    require.python.install_requirements('/usr/share/monitor_kraken/requirements.txt',
                                        use_sudo=True,
                                        exists_action='w')


@task
@roles('eng')
def get_no_data_instances():
    """ Get instances that have no data loaded ("status": null)"""
    for instance in env.instances.values():
        instance_has_data = test_kraken(instance.name, fail_if_error=False)
        if not instance_has_data:
            target_file = instance.kraken_database
            if not exists(target_file):
                print(blue("NOTICE: no data for {}, append it to exclude list"
                           .format(instance.name)))
                #we need to add a property to instances
                env.excluded_instances.append(instance.name)
            else:
                print(red("CRITICAL: instance {} is not available but *has* a "
                    "{}, please inspect manually".format(instance.name, target_file)))


@task
@serial
@roles('eng')
def disable_rabbitmq_standalone():
    """ Disable rabbitmq via network or by changing tyr configuration
        We can't just stop rabbitmq as tyr need it to start
    """

    for instance in env.instances.values():
        if env.dry_run is False:
            # break kraken configuration and restart all instances to enable it
            sed("%s/%s/kraken.ini" % (env.kraken_basedir, instance.name),
                "^port = %s$" % env.KRAKEN_RABBITMQ_OK_PORT,
                "port = %s" % env.KRAKEN_RABBITMQ_WRONG_PORT)
            restart_kraken(instance, test=False)


@task
@serial
@roles('eng')
def enable_rabbitmq_standalone():
    """ Enable rabbitmq via network or by changing tyr configuration
    """

    for instance in env.instances.values():
        if env.dry_run is False:
            # restore kraken configuration and restart all instances to enable it
            sed("%s/%s/kraken.ini" % (env.kraken_basedir, instance.name),
                "^port = %s$" % env.KRAKEN_RABBITMQ_WRONG_PORT,
                "port = %s" % env.KRAKEN_RABBITMQ_OK_PORT)
            restart_kraken(instance, test=False)


@task
@roles('eng')
def restart_all_krakens(wait=True):
    """restart and test all kraken instances"""
    wait = get_bool_from_cli(wait)
    start_or_stop_with_delay('apache2', env.APACHE_START_DELAY * 1000, 500, only_once=env.APACHE_START_ONLY_ONCE)
    for instance in env.instances.values():
        restart_kraken(instance.name, wait=wait)

@task
@roles('eng')
def test_all_krakens(wait=False):
    """test all kraken instances"""
    wait = get_bool_from_cli(wait)
    for instance in env.instances.values():
        test_kraken(instance.name, fail_if_error=False, wait=wait, loaded_is_ok=True)

@task
def test_these_krakens(*hosts):
    """test all kraken instances on a list of hosts
    """
    for host in hosts:
        with settings(host=get_host_addr(host)):
            test_all_krakens(True)

@task
@roles('eng')
def restart_kraken(instance, test=True, wait=True):
    """Restart a kraken instance on a given server
        To let us not restart all kraken servers in the farm
    """
    instance = get_real_instance(instance)
    wait = get_bool_from_cli(wait)
    if instance.name not in env.excluded_instances:
        kraken = 'kraken_' + instance.name
        start_or_stop_with_delay(kraken, 4000, 500, start=False, only_once=True)
        start_or_stop_with_delay(kraken, 4000, 500, only_once=env.KRAKEN_START_ONLY_ONCE)
        if test:
            test_kraken(instance.name, fail_if_error=False, wait=wait)
    else:
        print(yellow("{} has no data, not testing it".format(instance.name)))

@task
@roles('eng')
def stop_kraken(instance):
    """Stop a kraken instance on all servers
    """
    instance = get_real_instance(instance)
    kraken = 'kraken_' + instance.name
    start_or_stop_with_delay(kraken, 4000, 500, start=False, only_once=True)

@task
def get_kraken_config(server, instance):
    """Get kraken configuration of a given instance"""

    instance = get_real_instance(instance)
    
    with settings(host_string=server):
        config_path = "%s/%s/kraken.ini" % (env.kraken_basedir, instance.name)

        # first get the configfile here
        temp_file = StringIO.StringIO()
        if exists(config_path):
            get(config_path, temp_file)
        else:
            print(red("ERROR: can't find %s" % config_path))
            exit(1)

        config = ConfigParser.RawConfigParser(allow_no_value=True)
        config.readfp(BytesIO(temp_file.getvalue()))

        if 'GENERAL' in config.sections():
            return config
        else:
            return None


def _test_kraken(query, fail_if_error=True):
    """
    poll on kraken monitor until it gets a 'running' status
    """
    print("calling : {}".format(query.get_full_url()))
    try:
        response = urlopen(query)
    except HTTPError as e:
        if fail_if_error:
            print("HTTP Error %s on %s" % (e.code, e.readlines()[0]))
            exit(1)
        else:
            # we want response a file so transform the string as stringio
            # now jor ws return a 503 when the instance is loading data
            response = StringIO.StringIO(e.readlines()[0])

    except Exception as e:
        print("Error when connecting to monitor: %s" % e)
        exit(1)

    return json.loads(response.read())


@task
@roles('eng')
def test_kraken(instance, fail_if_error=True, wait=False, loaded_is_ok=None):
    """Test kraken with '?instance='"""
    
    instance = get_real_instance(instance)
    wait = get_bool_from_cli(wait)

    # env.host will call the monitor kraken on the current host
    request = Request('http://{}:{}/{}/?instance={}'.format(env.host,
        env.kraken_monitor_port, env.kraken_monitor_location_dir, instance.name))

    if wait:
        # we wait until we get a gestion and the instance is 'loaded'
        try:
            result = Retrying(stop_max_delay=env.KRAKEN_RESTART_DELAY * 1000,
                            wait_fixed=1000, retry_on_result=lambda x: x is None or not x['loaded']) \
                .call(_test_kraken, request, fail_if_error)
        except Exception as e:
            print(red("ERROR: could not reach {}, too many retries ! ({})".format(instance.name, e)))
            result = {'status': False}

    else:
        result = _test_kraken(request, fail_if_error)

    if result['status'] != 'running':
        if result['status'] == 'no_data':
            print(yellow("WARNING: instance {} has no loaded data".format(instance.name)))
            return False
        if fail_if_error:
            print(red("ERROR: Instance {} is not running ! ({})".format(instance.name, result)))
            return False
        print(yellow("WARNING: Instance {} is not running ! ({})".format(instance.name, result)))
        return False

    if not result['is_connected_to_rabbitmq']:
        print(yellow("WARNING: Instance {} is not connected to rabbitmq".format(instance.name)))
        return False

    if loaded_is_ok is None:
        loaded_is_ok = wait
    if not loaded_is_ok:
        if result['loaded']:
            print(yellow("WARNING: instance {} has loaded data".format(instance.name)))
            return True
        else:
            print(green("OK: instance {} has correct values: {}".format(instance.name, result)))
            return False
    else:
        if result['loaded']:
            print(green("OK: instance {} has correct values: {}".format(instance.name, result)))
            return True
        elif fail_if_error:
            print(red("CRITICAL: instance {} has no loaded data".format(instance.name)))
            exit(1)
        else:
            print(yellow("WARNING: instance {} has no loaded data".format(instance.name)))
            return False

@task
@roles('eng')
def disable_rabbitmq_kraken():
    """ Disable kraken rabbitmq connection through iptables
    """

    if env.dry_run is True:
        print("iptables --append OUTPUT --protocol tcp -m tcp --dport 5672 --jump DROP")
    else:
        run("iptables --flush")
        run("iptables --append OUTPUT --protocol tcp -m tcp --dport 5672 --jump DROP")


@task
@roles('eng')
def enable_rabbitmq_kraken():
    """ Enable kraken rabbitmq connection through iptables
    """
    if env.dry_run is True:
        print("iptables --delete OUTPUT --protocol tcp -m tcp --dport 5672 --jump DROP")
    else:
        run("iptables --delete OUTPUT --protocol tcp -m tcp --dport 5672 --jump DROP")

@task
@roles('eng')
def update_monitor_configuration():

    _upload_template('kraken/monitor_kraken.wsgi.jinja', env.kraken_monitor_wsgi_file,
            context={'env': env})
    _upload_template('kraken/monitor_settings.py.jinja', env.kraken_monitor_config_file,
            context={'env': env})


@task
@roles('eng')
def update_eng_instance_conf(instance):
    instance = get_real_instance(instance)
    _upload_template("kraken/kraken.ini.jinja", "%s/%s/kraken.ini" %
                     (env.kraken_basedir, instance.name),
                     context={
                         'env': env,
                         'instance': instance,
                     }
    )

    _upload_template("kraken/kraken.initscript.jinja",
                     "/etc/init.d/kraken_%s" % instance.name,
                     context={'env': env,
                              'instance': instance.name,
                              'kraken_base_conf': env.kraken_basedir,
                     },
                     mode='755'
    )

@task
@roles('eng')
def create_eng_instance(instance):
    """Create a new kraken instance
        * Install requirements (idem potem)
        * Deploy the binary, the templatized ini configuration in a dedicated
          directory with rights to www-data and the logdir
        * Deploy initscript and add it to startup
        * Start the service
    """
    instance = get_real_instance(instance)

    # base_conf
    require.files.directory(instance.kraken_basedir,
                            owner=env.KRAKEN_USER, group=env.KRAKEN_USER, use_sudo=True)

    # logs
    require.files.directory(env.kraken_log_basedir,
                            owner=env.KRAKEN_USER, group=env.KRAKEN_USER, use_sudo=True)

    require.files.directory(instance.base_destination_dir,
                            owner=env.KRAKEN_USER, group=env.KRAKEN_USER, use_sudo=True)

    update_eng_instance_conf(instance)

    # kraken.ini, pid and binary symlink
    if not exists("{}/{}/kraken".format(env.kraken_basedir, instance.name)):
        kraken_bin = "{}/{}/kraken".format(env.kraken_basedir, instance.name)
        files.symlink("/usr/bin/kraken", kraken_bin, use_sudo=True)
        sudo('chown {user} {bin}'.format(user=env.KRAKEN_USER, bin=kraken_bin))

    #run("chmod 755 /etc/init.d/kraken_{}".format(instance))
    sudo("update-rc.d kraken_{} defaults".format(instance.name))
    print(blue("INFO: Kraken {instance} instance is starting on {server}, "
               "waiting 5 seconds, we will check if processus is running".format(
        instance=instance.name, server=get_host_addr(env.host_string))))

    service.start("kraken_{} start".format(instance.name))
    run("sleep 5")  # we wait a bit for the kraken to pop

    # test it !
    # execute(test_kraken, get_host_addr(env.host_string), instance, fail_if_error=False)
    print("server: {}".format(env.host_string))
    run("pgrep --list-name --full {}".format(instance.name))
    print(blue("INFO: kraken {instance} instance is running on {server}".
               format(instance=instance.name, server=get_host_addr(env.host_string))))


@task
@roles('eng')
def remove_kraken_instance(instance, purge_logs=False):
    """Remove a kraken instance entirely
        * Stop the service
        * Remove startup at boot time
        * Remove initscript
        * Remove configuration and pid directory
    """
    instance = get_real_instance(instance)

    sudo("service kraken_%s stop; sleep 3" % instance.name)

    run("update-rc.d -f kraken_%s remove" % instance.name)
    run("rm --force /etc/init.d/kraken_%s" % instance.name)
    run("rm --recursive --force %s/%s/" % (env.kraken_basedir, instance.name))
    if purge_logs:
        # ex.: /var/log/kraken/navitia-bretagne.log
        run("rm --force %s-%s.log" % (env.kraken_log_name, instance.name))


@task
@roles('eng')
def rename_kraken_instance(instance):
    """Rename a kraken instance"""
    pass
