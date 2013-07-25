#!/usr/bin/env python
"""Example script that uses wolphin"""

import argparse
import sys

from fabric.api import run

from wolphin.project import WolphinProject, print_status
from wolphin.config import configuration
from wolphin.generator import wolphin_project


def controller():

    commands = [
        'status',
        'create',
        'start',
        'stop',
        'reboot',
        'terminate',
        'revert',
        'info'
    ]

    parser = argparse.ArgumentParser(description='Wolphin uses its cousin Boto, to manage the '
                                                 'Amazon ec2 instances for your projects.')

    parser.add_argument("command",
                        help=", ".join(commands))

    parser.add_argument("-p", "--project",
                        dest="project",
                        help="A unique name for your project.")

    parser.add_argument("--email",
                        dest="email",
                        help="Email of the project owner.")

    parser.add_argument("-a", "--auth",
                        dest="auth_credentials_file",
                        type=argparse.FileType('r'),
                        help="Path to the file containing authentication "
                             "credentials for amazon/ec2.")

    parser.add_argument("-c", "--config",
                        dest="user_ec2_args_file",
                        type=argparse.FileType('r'),
                        help="Path to the file containing overrides for the default wolphin "
                             "project configuration.")

    parser.add_argument("-i", "--instance",
                        nargs='*',
                        dest="project_instances",
                        help="Host(Instance) number (XXX of wolphin.<project.XXX>) of the wolphin "
                             "project instance to execute any of the wolphin commands.")

    parser.add_argument("-s", "--sequential",
                        dest="sequential",
                        action="store_true",
                        help="Used with the 'revert' command to indicate that reverting "
                             "should be done  sequentially: instance by instance and not in "
                             "a batch. Use this option if there is a risk of running of available "
                             " instances on ec2 if relinquished in bulk.")

    args, extra = parser.parse_known_args()

    if args.auth_credentials_file is None:
        parser.error("credentials required.")

    project = WolphinProject(configuration(auth_credentials_file=args.auth_credentials_file,
                                           project=args.project,
                                           email=args.email,
                                           user_config_file=args.user_ec2_args_file))

    if args.command == "status":
        status_info = project.status(instance_numbers=args.project_instances)
    elif args.command == "create":
        status_info = project.create()
    elif args.command == "info":
        for _ in wolphin_project(project, instance_numbers=args.project_instances):
            run("uname -aimnprsv; users; cat ~/.ssh/authorized_keys; ifconfig -a; pwd; ls -al")
    elif args.command == "start":
        status_info = project.start(instance_numbers=args.project_instances)
    elif args.command == "stop":
        status_info = project.stop(instance_numbers=args.project_instances)
    elif args.command == "reboot":
        status_info = project.reboot(instance_numbers=args.project_instances)
    elif args.command == "terminate":
        status_info = project.terminate(instance_numbers=args.project_instances)
    elif args.command == "revert":
        status_info = project.revert(instance_numbers=args.project_instances,
                                     sequential=args.sequential)
    else:
        parser.error("Unknown wolphin command: {}".format(args.command))

    if args.command != "info":
        print_status(status_info)

    sys.exit(0)

if __name__ == '__main__':
    controller()
