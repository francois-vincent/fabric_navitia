# encoding: utf-8

import os

from fabric.api import env

ROOTDIR = os.path.dirname(os.path.abspath(__file__))
SSH_KEY_FILE = os.path.join(ROOTDIR, '..', 'images', 'keys', 'unsecure_key')


def env_common(tyr, ed, kraken, jormun):
    env.hosts_tyr, env.hosts_ed, env.hosts_kraken, env.hosts_jormun = tyr, ed, kraken, jormun
    tyr_ssh, ed_ssh, kraken_ssh, jormun_ssh = env.make_ssh_url(tyr, ed, kraken, jormun)
    env.key_filename = SSH_KEY_FILE
    env.use_ssh_config = True
    env.use_syslog = False
    env.use_load_balancer = False

    env.roledefs = {
        'tyr':  tyr_ssh,
        'tyr_master': tyr_ssh[:1],
        'db':   ed_ssh,
        'eng':  kraken_ssh,
        'ws':   jormun_ssh
    }

    env.excluded_instances = []
    env.manual_package_deploy = True
    env.setup_apache = True

    env.kraken_monitor_listen_port = 85
    env.jormungandr_save_stats = False
    env.jormungandr_is_public = True
    env.tyr_url = 'localhost:6000'

    env.tyr_backup_dir_template = '/srv/ed/data/{instance}/backup/'
    env.tyr_source_dir_template = '/srv/ed/data/{instance}'
    env.tyr_base_destination_dir = '/srv/ed/data/'

    # env.jormungandr_url = jormun

    env.jormungandr_url_prefix = '/navitia'

    base_apache_conf = '/etc/apache2/conf.d' if env.distrib == 'debian7' else '/etc/apache2/conf-enabled'
    env.jormungandr_apache_config_file = os.path.join(base_apache_conf, 'jormungandr.conf')
    env.kraken_monitor_apache_config_file = os.path.join(base_apache_conf, 'monitor-kraken.conf')
