# encoding: utf-8

from collections import Mapping
import os
import time

import utils

ROOTDIR = os.path.dirname(os.path.abspath(__file__))


def get_containers(filter=None, all=True):
    """ Get containers names, with optional filter on name.
    :param filter: if string, get containers names containing it, if container, get images in this set.
    :param all: if False, get only running containers, else get all containers.
    :return:
    """
    docker_ps = utils.Command('docker ps -a' if all else 'docker ps').stdout_column(-1, 1)
    if filter:
        if isinstance(filter, basestring):
            return [x for x in docker_ps if filter in x]
        else:
            return [x for x in docker_ps if x in filter]
    return [x for x in docker_ps]


def get_images(filter=None):
    """ Get images names, with optional filter on name.
    :param filter: if string, get images names containing it, if container, get images in this set.
    :return:
    """
    docker_images = utils.Command('docker images').stdout_column(0, 1)
    if filter:
        if isinstance(filter, basestring):
            return [x for x in docker_images if filter in x]
        else:
            return [x for x in docker_images if x in filter]
    return [x for x in docker_images]


def container_delete(container):
    return utils.command('docker rm ' + container)


def container_stop(container):
    return utils.command('docker stop ' + container)


def image_delete(image):
    return utils.command('docker rmi ' + image)


def image_delete_and_containers(image):
    """ WARNING: This will remove an image and all its dependant containers
    """
    for container in utils.extract_column(utils.filter_column(utils.Command('docker ps').stdout, 1, eq=image), -1):
        container_stop(container)
    for container in utils.extract_column(utils.filter_column(utils.Command('docker ps -a').stdout, 1, eq=image), -1):
        container_delete(container)
    return image_delete(image)


def docker_build(context, image, tag=None):
    cmd = 'docker build -f {}/Dockerfile{} .'.format(image, ' -t {}'.format(tag) if tag else '')
    print(utils.yellow(cmd))
    with utils.cd(context):
        return utils.Command(cmd, show='Build: ').returncode


def docker_run(image, container=None, host=None, parameters=None):
    cmd = 'docker run -d '
    if container:
        cmd += '--name {} '.format(container)
    if host:
        cmd += '-h {} '.format(host)
    if parameters:
        cmd += parameters + ' '
    cmd += image
    print(utils.yellow(cmd))
    return utils.command(cmd)


def docker_start(container):
    return utils.command('docker start {}'.format(container))


def docker_commit(container, image):
    return utils.command('docker commit {} {}'.format(container, image))


def get_container_ip(container, raises=False):
    cmd = utils.Command("docker inspect --format '{{ .NetworkSettings.IPAddress }}' %s" % container)
    if raises and cmd.stderr:
        raise RuntimeError("Container {} is not running".format(container))
    return cmd.stdout.strip()


def docker_exec(container, cmd, user=None, stdout_only=True, return_code_only=False, raises=False):
    docker_cmd = 'docker exec -i {} {} {}'.format('-u {}'.format(user) if user else '', container, cmd)
    if return_code_only:
        return utils.command(docker_cmd)
    dock = utils.Command(docker_cmd)
    if raises and dock.returncode:
        raise RuntimeError(
            "Error while executing <{}>: [{}]".format(docker_cmd, dock.stderr.strip() or dock.returncode))
    if stdout_only:
        return dock.stdout.strip()
    return dock


def path_exists(path, container):
    return not docker_exec(container, 'test -e {}'.format(path), return_code_only=True)


def put_data(data, dest, container, append=False, user=None, perms=None):
    if append and not path_exists(dest, container):
        docker_exec(container, 'touch {}'.format(dest), user=user)
    cmd = ''.join(('echo "', data, '" >>' if append else '" >', dest))
    docker_exec(container, "/bin/sh -c '{}'".format(cmd), user=user, raises=True)
    if perms:
        utils.command('docker exec {} chmod {} {}'.format(container, perms, dest))


def get_data(source, container):
    return docker_exec(container, 'cat {}'.format(source), raises=True)


def put_file(source, dest, container, user=None, perms=None):
    # TODO
    pass


def get_version(app, container):
    text = docker_exec(container, 'apt-cache policy {}'.format(app), user='root')
    try:
        return utils.extract_column(utils.filter_column(text, 0, startswith='Install'), 1, sep=':')[0]
    except IndexError:
        return None


def wait_running_command(cmd, container, timeout=1):
    count, step = timeout, 0.2
    while count > 0:
        if cmd in docker_exec(container, 'ps ax'):
            return True
        time.sleep(step)
        count -= step
    return False


class PlatformManager(object):
    """
    Class in charge of bringing up a running platform and performing other docker magic
    Check existence or creates the images,
    then check existence or runs the containers.
    Optionally, stops and commits the containers.
    """

    def __init__(self, platform, images, parameters=(), user='root'):
        """
        :param platform: string
        :param images: dictionary/pair iterable of container-name:image
        :param parameters: dictionary/pair iterable of container-name:iterable of strings
        """
        self.images_rootdir = ROOTDIR
        self.platform_name = platform
        self.platform = self
        self.user = user
        self.images = images if isinstance(images, Mapping) else dict(images)
        self.parameters = parameters if isinstance(parameters, Mapping) else dict(parameters)
        self.containers = {k: '-'.join((v, self.platform_name, k)) for k, v in self.images.iteritems()}
        self.images_names = set(self.images.values())
        self.containers_names = self.containers.values()
        self.managers = {}

    def register_manager(self, name, manager):
        self.managers[name] = manager
        return self

    def get_manager(self, name):
        return self.managers.get(name)

    def host_from_container(self, container):
        for k, v in self.containers.iteritems():
            if v == container:
                return k
        raise LookupError("container {} not found".format(container))

    def setup(self, reset=None):
        """
        1- ensures images are created, otherwise, creates them
        2- ensures containers are created and started otherwise creates and/or starts them
        """
        self.build_images(reset)
        self.run_containers()
        return self

    def reset(self, reset='rm_image'):
        """ Resets a platform
        :param reset: 'uproot': remove platform images and any dependant container
                      'rm_image': remove platform images and containers
                      'rm_container': remove and stop platform containers
                      'stop': stop platform containers
        """
        if not reset:
            return self
        if reset == 'uproot':
            self.images_delete(uproot=True)
            return self
        if reset in ('stop', 'rm_container', 'rm_image'):
            self.containers_stop()
        if reset in ('rm_container', 'rm_image'):
            self.containers_delete()
        if reset == 'rm_image':
            self.images_delete()
        return self

    def build_images(self, reset=None):
        self.reset(reset)
        existing = self.get_real_images()
        for image in self.images_names:
            if image not in existing:
                print(utils.yellow("Build image {}".format(image)))
                docker_build(os.path.join(self.images_rootdir, 'images'), image, image)
        return self

    def images_exist(self):
        return self.images_names == set(self.get_real_images())

    def run_containers(self, reset=None):
        if reset in ('rm_image', 'uproot'):
            raise RuntimeError("Can't remove images before running containers")
        self.reset(reset)
        running = self.get_real_containers()
        existing = self.get_real_containers(True)
        for k, v in self.images.iteritems():
            container = self.containers[k]
            if container in running:
                continue
            if container in existing:
                docker_start(container)
            else:
                docker_run(v, container, container, self.parameters.get(k))
        return self

    def get_real_images(self):
        return get_images(self.images_names)

    def get_real_containers(self, all=False):
        return get_containers(self.containers_names, all)

    def images_delete(self, uproot=False):
        func = image_delete_and_containers if uproot else image_delete
        for image in self.get_real_images():
            print(utils.red("Delete image {}".format(image)))
            func(image)
        return self

    def containers_stop(self):
        for container in self.get_real_containers():
            print(utils.yellow("Stop container {}".format(container)))
            container_stop(container)
        return self

    def containers_delete(self):
        for container in self.get_real_containers(True):
            print(utils.yellow("Delete container {}".format(container)))
            container_delete(container)
        return self

    def get_hosts(self, raises=False):
        """ Returns the dict(host, ip) of containers actually running, or raises
           an exception if the number of running containers differs from the number
           of defined containers.
        """
        self.hosts_ips = {k: get_container_ip(v) for k, v in self.containers.iteritems()}
        if raises:
            if not all(self.hosts_ips.values()):
                expected = len(self.containers)
                found = len([x for x in self.hosts_ips.itervalues() if x])
                raise RuntimeError("Expecting {} running containers, found {}".format(expected, found))
        return self.hosts_ips

    def wait_process(self, proc, raises=True):
        for container in self.containers.itervalues():
            if not wait_running_command(proc, container):
                if raises:
                    raise RuntimeError("Container {} has no running '{}'".format(container, proc))
                return
        return True

    def ssh(self, cmd, host=None):
        """ this method requires that an ssh daemon is running on the target
            and that an authorized_keys file is set with a rsa plubilc key,
            all conditions met by images provided in this project.
        """
        if host:
            return utils.ssh(self.user, get_container_ip(self.containers[host]), cmd)
        return {k: utils.ssh(self.user, get_container_ip(v), cmd) for k, v in self.containers.iteritems()}

    def scp(self, source, dest, host=None):
        """ this method requires that an ssh daemon is running on the target
            and that an authorized_keys file is set with a rsa plubilc key,
            all conditions met by images provided in this project.
        """
        containers = [self.containers[host]] if host else self.containers.itervalues()
        for container in containers:
            utils.scp(source, dest, get_container_ip(container), self.user)
        return self

    def ssh_put_data(self, data, dest, host=None, append=False):
        if not append:
            self.ssh('touch {}'.format(dest), host)
        cmd = ''.join(('echo "', data, '" >>' if append else '" >', dest))
        self.ssh(cmd, host)
        return self

    def ssh_get_data(self, source, host=None):
        return self.ssh('cat {}'.format(source), host)

    def docker_exec(self, cmd, host=None):
        if host:
            return docker_exec(self.containers[host], cmd)
        return {k: docker_exec(v, cmd) for k, v in self.containers.iteritems()}

    def put_data(self, data, dest, host=None, append=False):
        containers = [self.containers[host]] if host else self.containers.itervalues()
        for container in containers:
            put_data(data, dest, container, append=append)
        return self

    def put_file(self, data, dest, host=None, append=False):
        containers = [self.containers[host]] if host else self.containers.itervalues()
        for container in containers:
            put_data(data, dest, container, append=append)
        return self

    def get_data(self, source, host=None):
        if host:
            return get_data(source, self.containers[host])
        return {k: get_data(source, v) for k, v in self.containers.iteritems()}

    def path_exists(self, path, host=None, negate=False):
        containers = [self.containers[host]] if host else self.containers.itervalues()
        for container in containers:
            if negate:
                if not path_exists(path, container):
                    continue
                print(utils.red("Found path <{}> on host <{}>".format(path, self.host_from_container(container))))
            else:
                if path_exists(path, container):
                    continue
                print(utils.red("Path <{}> not found on host <{}>".format(path, self.host_from_container(container))))
            return False
        return True

    def get_version(self, app, host=None):
        if host:
            return get_version(app, self.containers[host])
        return {k: get_version(app, v) for k, v in self.containers.iteritems()}

    def commit_containers(self, images, stop=True):
        if stop:
            self.containers_stop()
        for k, v in self.containers.iteritems():
            print(utils.yellow("commit {} to {}".format(v, images[k])))
            docker_commit(v, images[k])
        return self

    def start_services(self, *args, **kwargs):
        """ start services on the platform
        :param args: sequence of services to start on all hosts.
        :param kwargs: key=host, value=sequence of services, or
                       key=service, value=sequence of hosts.
        """
        wait = kwargs.pop('wait', None)
        for service in args:
            self.docker_exec('service {} start'.format(service))
        hosts_keys = set(kwargs).issubset(set(self.images.keys()))
        for k, v in kwargs.iteritems():
            for x in v:
                if hosts_keys:
                    self.docker_exec('service {} start'.format(x), k)
                else:
                    self.docker_exec('service {} start'.format(k), x)
        if wait:
            self.wait_process(wait)

    def docker_diff(self):
        # TODO this could only be useful if krakens were started in Dockerfile
        pass


class DeployedPlatformManager(PlatformManager):
    """ Class that manages the deployed platform, essentially through specific images and
        containers names, plus a setup function constructing these images and containers.
        Here the subclass PlatformManager is used as a mixin (constructor not called).
    """

    def __init__(self, platform, distri):
        self.platform = platform
        self.platform_name = platform.platform_name
        self.user = platform.user
        self.parameters = platform.parameters
        self.distri = distri
        self.images = {k: '-'.join((v, self.platform_name, k)) for k, v in platform.images.iteritems()}
        self.containers = {k: '-'.join((v, 'deployed')) for k, v in self.images.iteritems()}
        self.images_names = set(self.images.values())
        self.containers_names = self.containers.values()
        self.managers = {}

    def setup(self, reset=None):
        fabric = self.platform.get_manager('fabric')
        self.reset(reset)
        if not self.images_exist():
            self.platform.setup('rm_container')
            fabric.set_platform(distrib=self.distri)
            fabric.deploy_from_scratch(True)
            self.platform.commit_containers(self.images)
        self.run_containers('rm_container')
        fabric.register_platform(self)
        fabric.set_platform(distrib=self.distri)
        return self
