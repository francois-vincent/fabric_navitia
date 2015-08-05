"""
This file contains some specific tasks not to be run everytime
"""
import os
from fabric.api import env
from fabric.colors import red
from fabric.context_managers import cd, warn_only
from fabric.contrib.files import exists
from fabric.decorators import task, roles, hosts
from fabric.operations import run, put, sudo
from fabric.tasks import execute

from fabfile import utils
from fabfile.component import db, tyr, kraken

@task
@roles('tyr_master')
def update_all_ed_databases_to_alembic():
    """
     Migrate ED database handled by bash scripts to alembic.

     Must be called only during the database migration to alembic (navitia 1.1.3 to 1.2.0)

     This function can be deleted after this migration
    """
    for i in env.instances.values():
        if exists("{env}/{instance}".format(env=env.ed_basedir, instance=i.name)):
            with cd("{env}/{instance}".format(env=env.ed_basedir, instance=i.name)):
                run("./update_db.sh settings.sh")
                run("PYTHONPATH=. alembic stamp 52b017632678")
                run("PYTHONPATH=. alembic upgrade head")
        else:
            print(red("ERROR: {env}/{instance} does not exists. skipping db update"
                      .format(env=env.ed_basedir, instance=i.name)))


@roles('tyr_master')
def cities_integration():
    """ Setup the cities module

    see https://github.com/CanalTP/puppet-navitia/pull/45 for more information
    """

    run("apt-get --yes install navitia-cities")
    run("pip install python-dateutil")

    # postgresql user + dedicated database
    postgresql_user = 'cities'
    postgresql_database = postgresql_user
    password = utils._random_generator()
    execute(db.create_postgresql_user, "cities", password)
    execute(db.create_postgresql_database, "cities")

    # init_db.sh
    execute(db.postgis_initdb, "cities")

    utils._upload_template("tyr/cities_alembic.ini.jinja",
                     "{}/cities_alembic.ini".format(env.tyr_basedir),
                     context={
                         'env': env,
                         'postgresql_database': postgresql_database,
                         'postgresql_user': postgresql_user,
                         'postgresql_password': password,
                     },
    )

    raw_input("Please add \"CITIES_DATABASE_URI = 'user={user} password={password} "
              "host={database_host} dbname={dbname}'\" in /srv/tyr/settings.py and press "
              "enter when finished.".format(password=password,
                                            database_host=env.postgresql_database_host,
                                            dbname=postgresql_database,
                                            user=postgresql_user))

    with cd(env.tyr_basedir):
        run("alembic --config cities_alembic.ini upgrade head")
        if exists("/srv/ed/france-latest.osm.pbf"):
            run("TYR_CONFIG_FILE=/srv/tyr/settings.py ./manage.py {} "
                "/srv/ed/france-latest.osm.pbf".format(postgresql_database))
    execute(tyr.restart_tyr_worker)


@task
@roles('tyr_master')
def deploy_all_default_synonyms():
    """
    add default synonyms to all instances
    this should not be necesary after the migration as
    all new instances are deployed with the default synonyms
    """
    default_synonyms_file = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                         os.path.pardir, 'static_files', 'ed', 'default_synonyms.txt')
    for i in env.instances.values():
        put(default_synonyms_file, i.source_dir, use_sudo=True)
        sudo("chown {u} {f}".format(u=env.KRAKEN_USER, f=os.path.join(i.source_dir, 'default_synonyms.txt')))


@task
@roles('ws', 'tyr', 'eng')
def install_system_python_protobuf():
    """
    force uninstall python protobuf to allow using system protobuf
    """
    sudo("apt-get update")
    sudo("apt-get --yes remove python-protobuf")
    sudo("apt-get --yes autoremove")
    with warn_only():
        sudo("pip uninstall --yes protobuf")
    sudo("! (pip freeze | grep -q protobuf)")
    sudo("apt-get --yes install python-protobuf")

try:
    eng_hosts_1 = env.eng_hosts_1
    eng_hosts_2 = env.eng_hosts_2
except AttributeError:
    eng_hosts_1 = ()
    eng_hosts_2 = ()

@task
@hosts(*eng_hosts_1)
def test_kraken1():
    """ specific prod task to check that kraken are started on eng1
    """
    for instance in env.instances.values():
        kraken.test_kraken(instance.name, fail_if_error=False, wait=True, loaded_is_ok=True)


@task
@hosts(*eng_hosts_2)
def test_kraken234():
    """ specific prod task to check that kraken are started on eng1, eng2 & eng3
    """
    for instance in env.instances.values():
        kraken.test_kraken(instance.name, fail_if_error=False, wait=True, loaded_is_ok=True)

