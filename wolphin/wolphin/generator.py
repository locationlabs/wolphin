from fabric.api import settings

from wolphin.exceptions import NoRunningInstances


def wolphin_project(project, instance_numbers=None):

    instances = project.get_healthy_instances(instance_numbers)
    for instance in instances:
        instance.update()
    running_instances = [i.ip_address for i in instances if i.state == 'running']

    if not running_instances:
        raise NoRunningInstances("project: {}".format(project.config.project))

    for host_string in running_instances:
        with settings(host_string=host_string,
                      user=project.config.user,
                      key_filename=project.config.ssh_key_file):
            yield
