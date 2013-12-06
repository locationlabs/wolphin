from fabric.api import settings

from wolphin.exceptions import NoRunningInstances


def wolphin_project(project, selector=None):

    running_hosts = project.get_instances_in_states([project.STATES['running']],
                                                    selector=selector)
    if not running_hosts:
        raise NoRunningInstances("project: {}".format(project.config.project))

    for host in [host.ip_address for host in running_hosts]:
        with settings(host_string=host,
                      user=project.config.user,
                      key_filename=project.config.ssh_key_file):
            yield
