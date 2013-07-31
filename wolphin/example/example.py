#!/usr/bin/env python
"""Example script that uses wolphin"""

import argparse
import sys

from fabric.api import run

from wolphin.project import WolphinProject, print_status
from wolphin.config import Configuration
from wolphin.generator import wolphin_project
from wolphin.exceptions import WolphinException
from wolphin.selector import InstanceNumberBasedSelector


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

    parser.add_argument("command", choices=commands)

    parser.add_argument("-p", "--project",
                        dest="project",
                        help="A unique name for your project.")

    parser.add_argument("--email",
                        dest="email",
                        help="Email of the project owner.")

    parser.add_argument("-c", "--config",
                        nargs='+',
                        dest="config_files",
                        type=argparse.FileType('r'),
                        help="Path to the file(s) containing overrides for the default wolphin "
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

    parser.add_argument("--log",
                        dest="logging_level",
                        default=Configuration.DEFAULT_LOGGING_LEVEL,
                        help="Set the logging level, e.g. '--log DEBUG' to set the level to DEBUG.")

    args, extra = parser.parse_known_args()

    config = Configuration.create(*args.config_files)
    config.email = args.email or config.email
    config.project = args.project or config.project
    config.logging_level = args.logging_level
    selector = InstanceNumberBasedSelector(instance_numbers=args.project_instances)
    project = WolphinProject.new(config)

    try:
        if args.command == "status":
            status_info = project.status(selector=selector)
        elif args.command == "create":
            status_info = project.create()
        elif args.command == "info":
            for _ in wolphin_project(project, selector=selector):
                run("uname -a; users")
        elif args.command == "start":
            status_info = project.start(selector=selector)
        elif args.command == "stop":
            status_info = project.stop(selector=selector)
        elif args.command == "reboot":
            status_info = project.reboot(selector=selector)
        elif args.command == "terminate":
            status_info = project.terminate(selector=selector)
        elif args.command == "revert":
            status_info = project.revert(sequential=args.sequential)

        if args.command != "info":
            print_status(status_info)

    except WolphinException as ex:
        print ex
        sys.exit(1)

if __name__ == '__main__':
    controller()
