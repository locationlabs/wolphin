from os.path import abspath, expanduser, join

from fabric.api import settings

from wolphin.exceptions import NoRunningInstances


def wolphin_project(project, instance_numbers=None):

    key_filename = abspath(expanduser(join(project.config['PEM_PATH'],
                                           project.config['PEM_FILE'])))

    running_instances = []
    for instance in project.get_healthy_instances(instance_numbers):
        instance.update()
        if instance.state_code == project.STATES['running']:
            running_instances.append("{}@{}".format(project.config['USER'], instance.ip_address))

    if not running_instances:
        raise NoRunningInstances(project.config['PROJECT'])

    for host_string in running_instances:
        with settings(host_string=host_string, key_filename=key_filename):
            yield
