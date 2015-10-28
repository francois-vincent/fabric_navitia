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

from fabric.colors import yellow
from fabric.context_managers import settings, warn_only
from fabric.decorators import task, roles
from fabric.operations import run, sudo
from fabric.tasks import execute
from fabric.api import env
from fabtools import require
from fabfile.utils import  get_psql_version, _upload_template


def instance2postgresql_name(instance):
    #DEPRECATED
    """Return the database name after applying our rules"""
    return "ed_{}".format(instance.replace('-', '_'))

@task
@roles('db')
def start_services():
    require.postgres.server()

@task
@roles('db')
def setup_db():
    require.postgres.server()
    require.deb.package("postgis")
    with warn_only():
        status_line = run(r'dpkg -s postgis | grep "Suggests\|Recommends"')
    for package in status_line.split():
        if "postgis" in package and "postgres" in package and not "doc" in package:
            require.deb.package(package.replace(',', ''))

    # db creation
    require.postgres.user(env.tyr_postgresql_user, env.tyr_postgresql_password)
    require.postgres.database(env.tyr_postgresql_database, owner=env.tyr_postgresql_user, locale='en_US.UTF-8')
    postgis_initdb(env.tyr_postgresql_database)

@task
@roles('db')
def postgis_initdb(instance_db):
    """Populate the a database with postgis
        The script init_db.sh is on tyr, but need to create a postgis extension
        on db, so load the sql scripts directly from db server
    """
    if db_has_postgis(instance_db):
        #postgis 2.0 with old postgres version does not seems to be idempotent, so we do the postgis init only once
        print "instance {} already has postgis, skiping postgis init".format(instance_db)
        return
    # # init_db.sh, create this on database host because sql scripts or @localhost
    # # and must be run as postgres user

    psql_version = get_psql_version()
    if psql_version[0:2] == ["9", "1"]:
        postgis_path = '/usr/share/postgresql/9.1/contrib/postgis-1.5'
        with settings(sudo_user='postgres'):
            sudo('psql --set ON_ERROR_STOP=1 --dbname={} '
                 '--file {}/postgis.sql'.format(instance_db, postgis_path))
            sudo('psql --set ON_ERROR_STOP=1 --dbname={}'
                ' --file {}/spatial_ref_sys.sql'.format(instance_db, postgis_path))
    elif psql_version[0:2] >= ["9", "3"]:
        with settings(sudo_user='postgres'):
            sudo('psql -c "CREATE EXTENSION  IF NOT EXISTS postgis;" --dbname={}'.format(instance_db))
    else:
        raise EnvironmentError("Bad version of postgres")

@task
@roles('db')
def set_tyr_is_free(instance, is_free=True):
    """Set is_free flag in jormungandr database for a given instance"""

    _upload_template("db/is-free.sql.jinja", \
            "/var/lib/postgresql/postgres_{}.sql".format(instance),
            context={
                'instance': instance,
                'is_free': is_free,
            }
    )
    run('su - postgres --command="psql {} < /var/lib/postgresql/postgres_{}.sql"'
            .format(env.jormungandr_postgresql_database, instance))
    run("rm -f /var/lib/postgresql/postgres_{}.sql".format(instance))

@task
@roles('db')
def check_is_postgresql_user_exist(username):
    """Check if a given postgresql user exist"""
    _upload_template("db/check_is_postgresql_user_exist.sql.jinja",
            "/var/lib/postgresql/postgres_{}.sql".format(username),
            context={
                'username': username,
            }
    )
    user = run('su - postgres --command="psql --tuples-only postgres < /var/lib/postgresql/postgres_{}.sql"'
               .format(username))
    run("rm -f /var/lib/postgresql/postgres_{}.sql".format(username))
    if username == user:
        return True
    else:
        return False

@task
@roles('db')
def create_postgresql_user(username, password):
    """ Create a postgresql user"""
    run('su - postgres --command="createuser {} --no-createdb --no-createrole --no-superuser"'.format(username))

    # set the password
    _upload_template("db/set_user_password.sql.jinja",
            "/var/lib/postgresql/postgres_{}.sql".format(username),
            context={
                'username': username,
                'password': password,
            }
    )
    run('su - postgres --command="psql postgres < /var/lib/postgresql/postgres_{}.sql"'.format(username))
    run("rm -f /var/lib/postgresql/postgres_{}.sql".format(username))

    # test the user access
    run('PGPASSWORD="{}" psql --tuples-only --host localhost --username {} '
        'postgres --command="SELECT * FROM pg_catalog.pg_database;"'.format(password, username))

@task
@roles('db')
def create_postgresql_database(database, username=None):
    """Create a postgresql database
        If no user provided, owner will be set same as database name
    """
    if not username:
        username = database

    run('su - postgres --command="createdb {database} --owner={username} --encoding=UTF8"'
            .format(database=database, username=username))

@task
@roles('db')
def rename_postgresql_database(current_database, new_database):
    """ Rename a postgresql database and the SAME corresponding username"""

    _upload_template("db/rename_postgresql_database_user.sql.jinja",
            "/var/lib/postgresql/postgres_{}.sql".format(current_database),
            context={
                'current_database': current_database,
                'new_database': new_database,
            }
    )
    run('su - postgres --command="psql postgres < /var/lib/postgresql/postgres_{}.sql"'.format(current_database))
    run("rm -f /var/lib/postgresql/postgres_{}.sql".format(current_database))

@task
@roles('db')
def remove_postgresql_database(database):
    """Remove a postgresql database"""
    run('su - postgres --command="dropdb {database}"'
            .format(database=database))

@task
@roles('db')
def remove_postgresql_user(username):
    """ Create a postgresql user"""
    run('su - postgres --command="dropuser {}"'.format(username))

@roles('db')
def is_postgresql_user_exist(username):
#   select exists (SELECT * FROM pg_user WHERE usename=\'ed_uk\');
    dbuserexist = run('sudo -i -u postgres psql -A -t -c "select exists (SELECT * FROM pg_user WHERE usename=\'{}\');"'
                      .format(username))
    return dbuserexist == 't'

@roles('db')
def is_postgresql_database_exist(dbname):
    dbnameexist = run('sudo -i -u postgres psql -A -t -c "select exists (SELECT * FROM pg_database '
                      'WHERE datname=\'{}\');"'.format(dbname))
    return dbnameexist == 't'


@roles('db')
def db_has_postgis(dbname):
    res = run('sudo -i -u postgres psql -A -t -c '
              '"select exists (select 1 from pg_type where typname = \'geography\');" {}'.format(dbname))
    return res == 't'


@task
@roles('db')
def remove_instance_from_jormun_database(instance):
    """Remove a given ed instance in jormungandr PostgreSQL db
        http://jira.canaltp.fr/browse/NAVITIAII-1098
    """
    _upload_template("db/remove_instance.sql.jinja", \
            "/var/lib/postgresql/postgres_{}.sql".format(instance),
            context={
                'instance': instance,
            }
    )
    run('su - postgres --command="psql jormungandr < /var/lib/postgresql/postgres_{}.sql"'.format(instance))
    run("rm -f /var/lib/postgresql/postgres_{}.sql".format(instance))


@task
@roles('db')
def rename_tyr_jormungandr_database(current_instance, new_instance):
    """ Rename the instance id in the jormungandr database """

    _upload_template("db/rename_tyr_jormungandr_database.sql.jinja", \
            "/var/lib/postgresql/postgres_{}.sql".format(current_instance),
            context={
                'current_database': current_instance,
                'new_database': new_instance,
            }
    )
    run('su - postgres --command="psql {} < /var/lib/postgresql/postgres_{}.sql"'
            .format(env.jormungandr_postgresql_database, current_instance))
    run("rm -f /var/lib/postgresql/postgres_{}.sql".format(current_instance))


@task
@roles('tyr_master')
def call_tyr_http_authorization(uid, instance_id):
    tyrhttpcommand = 'curl --header \'Host: {}\' "http://localhost/v0/users/{}/authorizations/" ' \
                     '--data "api_id=1&instance_id={}"'.format(env.tyr_url, uid, instance_id)
    run(tyrhttpcommand)

@task
@roles('db')
def set_instance_authorization(instance):
    # Utilisation de "sudo -u" pour la gestion des simples cote '' apres le "where"
    # Utilisation du parametre "-i" de sudo pour eviter la redirection 'could not change directory to "/root"'
    # Utilisation du parametre "-A" de psql pour suprimer la ligne dans le resultat de la requete sql
    # Utilisation de parametre "-t" de psql pour afficher uniquement le resultat du "select"
    instance_id = run('sudo -i -u postgres psql -A -t --dbname={} '
                      '-c "select id from instance where name = \'{}\';"'
                      .format(env.jormungandr_postgresql_database, instance))
    uid = run('sudo -i -u postgres psql -A -t --dbname={} -c "select user_id from key '
              'where token = \'{}\';"'.format(env.jormungandr_postgresql_database, env.token))
    if instance_id.isdigit() and uid.isdigit():
        execute(call_tyr_http_authorization, uid, instance_id)
    else:
        print(yellow("WARNING: Le token d'administration n'a pas été appliqué sur l'instance!!!"))

@task
@roles('db')
def create_instance_db(instance):
    
    postgresql_user = instance.db_user
    postgresql_database = instance.db_name

    require.postgres.user(postgresql_user, instance.db_password)
    require.postgres.database(postgresql_database, postgresql_user)


@task
@roles('db')
def create_kirin_db():

    user, password, database = ('kirin', ) * 3
    pwd = raw_input(yellow("Please enter password (default=kirin): "))
    if pwd:
        password = pwd

    require.postgres.user(user, password)
    require.postgres.database(database, user)
