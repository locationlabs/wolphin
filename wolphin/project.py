import logging
from time import sleep

from boto.exception import EC2ResponseError
from boto.ec2 import connect_to_region
from fabric.api import hide, run, settings
from gusset.colortable import ColorTable

from wolphin.attribute_dict import AttributeDict
from wolphin.exceptions import EC2InstanceLimitExceeded, SSHTimeoutError, WolphinException
from wolphin.selector import DefaultSelector


class WolphinProject(object):

    def __init__(self, config, conn):
        self.STATES = {
            'pending': 0,
            'running': 16,
            'shutting-down': 32,
            'stopping': 64,
            'stopped': 80,
            'terminated': 48
        }
        self.config = config
        self.conn = conn
        self.logger = logging.getLogger('wolphin.{}'.format(config.project))

    @classmethod
    def new(cls, config):
        """
        Factory method to create a new instance of WolphinProject.

        :param config: `class:wolphin.config.Configuration` object to configure the project with.
        :returns: `class:wolphin.project.WolphinProject`.
        """

        config.validate()
        conn = connect_to_region(config.region,
                                 aws_access_key_id=config.aws_access_key_id,
                                 aws_secret_access_key=config.aws_secret_key)
        project = cls(config, conn)

        return project

    def create(self, wait_for_ssh=True):
        """
        Creates a new wolphin project and the requested number of ec2 instances for the project.

        :param wait_for_ssh: (optional) defaults to True, set to False if wolphin should not wait
         for the project's ec2 instances to be ssh-ready.
        """

        self.logger.info("Finding any existing reusable hosts .... ")

        # now wait for the shutting-down and stopping instances to finish shutting down / stopping.
        self._wait_for_shutting_down_instances()
        self._wait_for_stopping_instances()

        healthy = self._get_healthy_instances()

        self._satisfy_config_requirements(healthy)

        # wait for all the healthy ones to be running.
        self.logger.info("Waiting for all instances to start ....")
        self._wait_for_transition(healthy, new_state_code=self.STATES['running'])

        if wait_for_ssh:
            self._wait_for_ssh(healthy)

        self.logger.info("{} ec2 instances ready for project"
                         .format(len(self.get_instances_in_states([self.STATES['running']]))))
        self.logger.info("Finished creating.")
        return self.status()

    def _satisfy_config_requirements(self, healthy):
        # terminate some existing ones if they are extra.
        already_present = len(healthy)
        max_number_needed = self.config.max_instance_count - already_present

        if max_number_needed < 0:
            self.logger.info("Terminating extra instances ....")
            self.terminate(instances=healthy[max_number_needed:])
            healthy = healthy[:max_number_needed]
        elif max_number_needed > 0:
            # reserve new instances.
            # boto requires minimum number of instances requested to be 1
            min_number_needed = max(1, self.config.min_instance_count - already_present)

            self.logger.info("More needed from Amazon: between {} and {} instances"
                             .format(min_number_needed, max_number_needed))
            new_instances = self._create_extra_instances(min_number_needed, max_number_needed)
            healthy.extend(new_instances)

        # start non running instances.
        for instance in healthy:
            if instance.state != 'running':
                instance.start()


    def _create_extra_instances(self, min_number_needed, max_number_needed):

        # get the max instance number to start tagging with. Do this before requesting instances
        # so that there is no lag between reservation and tagging.
        instance_allocation_number = self._max_allocated_number()

        self.logger.debug("Requesting between {} and {} EC2 instances ...."
                          .format(min_number_needed, max_number_needed))

        reservation = self._reserve(min_number_needed, max_number_needed)
        provided = len(reservation.instances)
        self.logger.debug("{} instances provided by Amazon".format(provided))

        instances = reservation.instances or []
        # Tagging instances with the project name.
        for tag_number, instance in enumerate(instances,
                                              start=instance_allocation_number + 1):
            self._tag_instance(instance, tag_number)
        return instances

    def _max_allocated_number(self):
        """Returns the maximum instance number allocated to this project's ec2 instances"""
        instances = self._get_all_instances()
        return (max(0, *[self._get_instance_number(instance) for instance in instances])
                if instances else 0)

    def start(self, selector=None, wait_for_ssh=True):
        """
        Start the appropriate ec2 instance(s) based on ``self.config``.

        :param selector: (optional) the `class:wolphin.selector.Selector` to be used.
        :param wait_for_ssh: (optional) defaults to True, set to False if wolphin should not wait
         for the project's ec2 instances to be ssh-ready.
        """

        # wait for the stopping instances to finish stopping as they cannot be started if
        # they are in the middle of stopping.
        self._wait_for_stopping_instances(selector=selector)

        # start the instances that are not already running, pending to start, or stopping.
        instances = self.get_instances_in_states([self.STATES['shutting-down'],
                                                  self.STATES['terminated'],
                                                  self.STATES['stopping'],
                                                  self.STATES['pending'],
                                                  self.STATES['running']],
                                                 inverse_select=True,
                                                 selector=selector)
        for instance in instances:
            instance.start()

        self._wait_for_starting_instances(instances=instances)

        if wait_for_ssh:
            instances = self.get_instances_in_states([self.STATES['running']],
                                                     selector=selector)
            self._wait_for_ssh(instances)

        self.logger.info("Finished starting.")
        return self.status(selector)

    def stop(self, selector=None):
        """Stop the appropriate ec2 instance(s)"""

        # wait for the starting instances to finish starting as they cannot be stopped if
        # they are in the middle of starting.
        self._wait_for_starting_instances(selector=selector)

        # stop the instances that are not already stopping, stopped or pending.
        instances = self.get_instances_in_states([self.STATES['shutting-down'],
                                                  self.STATES['terminated'],
                                                  self.STATES['pending'],
                                                  self.STATES['stopping'],
                                                  self.STATES['stopped']],
                                                 inverse_select=True,
                                                 selector=selector)
        for instance in instances:
            instance.stop()

        self._wait_for_stopping_instances(instances=instances)
        self.logger.info("Finished stopping.")
        return self.status(selector)

    def reboot(self, selector=None):
        self.stop(selector)
        self.start(selector)
        self.logger.info("Finished rebooting.")
        return self.status(selector)

    def revert(self, sequential=False, selector=None):
        """Revert project instances"""

        instances = self._get_healthy_instances(selector)
        self.logger.info("Starting reverting {} instances ....".format(len(instances)))

        if instances and sequential:
            self.logger.info("sequentially ....")
            for instance in instances:
                self._revert([instance])

        elif instances:
            self.logger.info("in a batch ....")
            self._revert(instances)

        self.logger.info("Finished reverting.")
        return self.status(selector)

    def _revert(self, instances):
        """
        Given the instances requested to be reverted:
        For each such instance:
         - saves the instance numbers
         - terminate instances
         - run new instances
         - tag each new instance with a previous instance number
        """

        instance_numbers = [self._get_instance_number(instance) for instance in instances]
        self.terminate(instances=instances)
        self.logger.debug("Getting a new reservation ....")
        if instance_numbers:
            new_instances = self._reserve(len(instance_numbers), len(instance_numbers)).instances
            self.logger.debug("{} instances received from Amazon.".format(len(new_instances)))

            for instance, instance_number in zip(new_instances, instance_numbers):
                self._tag_instance(instance, instance_number)

            self._wait_for_starting_instances(instances=new_instances)

    def status(self, selector=None):
        """Returns the statuses of requested wolphin project instances"""

        as_attribute_dict = (lambda instance:
                             AttributeDict(id=instance.id,
                                           project_name=instance.tags.get("ProjectName"),
                                           name=instance.tags.get("Name"),
                                           state_code=instance.state_code,
                                           state=instance.state,
                                           public_dns_name=instance.public_dns_name,
                                           public_ip_address=instance.ip_address,
                                           private_dns_name=instance.private_dns_name,
                                           private_ip_address=instance.private_ip_address,
                                           ami_id=instance.image_id,
                                           instance_type=instance.instance_type,
                                           placement=instance.placement,  # availability zone
                                           ssh_key_name=instance.key_name,
                                           security_groups=instance.groups,
                                           launch_time=instance.launch_time,
                                           owner_email=instance.tags.get("OwnerEmail")))

        return [as_attribute_dict(instance)
                for instance in self._select_instances(selector=selector)]

    def terminate(self, instances=None, selector=None):
        """
        Terminate instances

        :param instances: a list of instances to terminate.
        :param force: if True, terminates all instances irrespective of any selectors applied.

        """
        instances_to_terminate = instances or self._get_healthy_instances(selector)
        for instance in instances_to_terminate:
            instance.terminate()

        self._wait_for_shutting_down_instances(instances_to_terminate)
        self.logger.info("Finished terminating.")
        return self.status(selector)

    def get_instances_in_states(self, state_codes, inverse_select=False, selector=None):
        """Returns project instances that are in the given ``state_codes``"""

        not_in_state = lambda instance: instance.state_code not in state_codes
        in_state = lambda instance: instance.state_code in state_codes
        filter_function = not_in_state if inverse_select else in_state
        instances = self._select_instances(selector)

        return filter(filter_function, instances)

    def _get_healthy_instances(self, selector=None):
        """
        Returns instances that are not terminated and not going towards termination (shutting-down).
        """

        return self.get_instances_in_states([self.STATES['terminated'],
                                             self.STATES['shutting-down']],
                                            inverse_select=True,
                                            selector=selector)

    def _get_all_instances(self):
        """Get all instances for a wolphin project on ec2"""

        reservations = self.conn.get_all_instances(filters={"tag:ProjectName":
                                                            "wolphin.{}"
                                                            .format(self.config.project)})

        return self._get_instances_from_reservations(reservations)

    def _get_instance_number(self, instance):
        """Parses the instance name to get the instance number"""

        return int(str((instance).tags.get("Name")).split(".")[-1])

    def _get_instances_from_reservations(self, reservations):
        """Flatten all reservations to get one instances list"""

        instances = [instance
                     for reservation in reservations or []
                     for instance in reservation.instances]

        for instance in instances:
            instance.update()

        return instances

    def _reserve(self, min_number_needed=None, max_number_needed=None):
        """
        Makes a reservation for ec2 instances, on amazon ec2, based on ``self.config`` parameters,
        starts the instances and returns the reservation.
        """

        min_number_needed = min_number_needed or self.config.min_instance_count
        max_number_needed = max_number_needed or self.config.max_instance_count

        # reserve and run instances.
        try:
            reservation = self.conn.run_instances(self.config.ami_id,
                                                  min_count=str(min_number_needed),
                                                  max_count=str(max_number_needed),
                                                  key_name=self.config.amazon_keypair_name,
                                                  security_groups=
                                                  [self.config.instance_securitygroup],
                                                  instance_type=self.config.instance_type,
                                                  placement=
                                                  self.config.instance_availabilityzone)
        except EC2ResponseError as ec2_error:
            if "InstanceLimitExceeded" in str(ec2_error):
                raise EC2InstanceLimitExceeded("EC2 instance limit exceeded in region={}"
                                               "\nAmazon EC2 Response:"
                                               "\n{}".format(self.config.region,
                                                             ec2_error))
            else:
                raise WolphinException(str(ec2_error))
        return reservation

    def _select_instances(self, selector=None):
        """Gets the instances based on self.config"""

        selector = selector or DefaultSelector()
        return selector.select(self._get_all_instances())

    def _tag_instance(self, instance, suffix):
        """
        Tag an ec2 ``instance`` by making its wolphin instance name's suffix as ``suffix``.
        ``self.config`` is used to construct the complete wolphin instance name.
        """

        self.conn.create_tags(instance.id,
                              {"Name": "wolphin.{}.{}".format(self.config.project, suffix),
                               "ProjectName": "wolphin.{}".format(self.config.project),
                               "OwnerEmail": self.config.email})

    def _wait_for_transition(self, instances, state_code=None, new_state_code=None):
        """
        Waits till the state code of the ``instances`` remains to be ``state_code``,
        if ``new_code is set, then waits till all the ``instances`` get to the ``new_state_code``.
        """

        if not instances:
            return
        for _ in range(self.config.max_wait_tries):
            if self._all_instances_have_transitioned(instances, state_code, new_state_code):
                break
            sleep(self.config.max_wait_duration)
        else:
            self.logger.warning("Timed out while waiting for instances' state transition, "
                                "will not wait anymore, continuing ....")

        return instances

    def _all_instances_have_transitioned(self, instances, state_code, new_state_code):
        self.logger.debug("Waiting for {} instances to go from {} to {} "
                          "(refreshed every {} secs., max {} secs.)"
                          .format(len(instances),
                                  _inverse_lookup(self.STATES, state_code),
                                  _inverse_lookup(self.STATES, new_state_code),
                                  self.config.max_wait_duration,
                                  self.config.max_wait_tries * self.config.max_wait_duration))

        all_instances_ready, status_table = self._check_instances_for_transition(instances,
                                                                                 state_code,
                                                                                 new_state_code)
        self.logger.debug("\n{}".format(status_table))
        return all_instances_ready

    def _check_instances_for_transition(self, instances, state_code, new_state_code):
        """
        Checks if the ``instances`` have transitioned out of the ``state_code`` to the
        ``new_state_code`` and returns True if all of them have, False otherwise along with the
        statuses of all of them.
        """

        keep_waiting = False
        status_table = ColorTable('instance', 'state')
        for instance in instances:
            instance.update()
            status_table.add(instance="{}|{}".format(instance.id, instance.tags.get("Name")),
                             state="{}|{}".format(instance.state_code, instance.state))

            if ((state_code is not None and instance.state_code == state_code) or
                    (new_state_code is not None and instance.state_code != new_state_code)):
                keep_waiting = True
        return not keep_waiting, status_table

    def _wait_for_ssh(self, instances):
        """
        Waits until the ``instances`` are ssh-ready.
        """

        if not instances:
            return
        for _ in range(self.config.max_wait_tries):
            if self._all_instances_ssh_ready(instances):
                break
            sleep(self.config.max_wait_duration)
        else:
            error_message = ("Timed out when waiting for some or all instances of project:"
                             "{} to be ssh-ready."
                             .format(self.config.project))
            self.logger.error(error_message)
            raise SSHTimeoutError(error_message)

        return instances

    def _all_instances_ssh_ready(self, instances):
        self.logger.debug("Waiting for {} instances to be ssh ready"
                          "(refreshed every {} secs., max {} times.)"
                          .format(len(instances),
                                  self.config.max_wait_duration,
                                  self.config.max_wait_tries))

        all_instances_ready, status_table = self._check_instances_for_ssh(instances)
        self.logger.debug("\n{}".format(status_table))
        return all_instances_ready

    def _check_instances_for_ssh(self, instances):
        """
        Checks if the ``instances`` are ssh-ready; returns True if they are, False otherwise,
        along with the statuses of all of them.
        """

        not_ready = False
        status_table = ColorTable('instance', 'ssh_ready')
        for instance in instances:
            instance.update()
            instance_is_ssh_ready = self._check_if_ssh_ready(instance)
            not_ready = not_ready or not instance_is_ssh_ready

            status_table.add(instance="{}|{}".format(instance.id, instance.tags.get("Name")),
                             ssh_ready=str(instance_is_ssh_ready))
        return not not_ready, status_table

    def _check_if_ssh_ready(self, instance):
        """
        Tries to ssh into an ``instance`` using the project's config; returns True if it was
        successful, False otherwise.
        """

        if not instance.ip_address:
            # if the host is not ready yet, it may not even have a host string
            # which would mean it is definitely not ready for ssh yet.
            return False
        try:
            with settings(hide('everything'),
                          host_string=instance.ip_address,
                          user=self.config.user,
                          key_filename=self.config.ssh_key_file):
                run("hostname")
        except:
            return False
        return True

    def _wait_for_starting_instances(self, instances=None, selector=None):
        self.logger.info("Waiting for pending instances to start ....")
        self._wait_for_transition(instances or
                                  self.get_instances_in_states([self.STATES['pending']],
                                                               selector=selector),
                                  state_code=self.STATES['pending'],
                                  new_state_code=self.STATES['running'])

    def _wait_for_shutting_down_instances(self, instances=None, selector=None):
        self.logger.info("Waiting for shutting-down instances to terminate ....")
        self._wait_for_transition(instances or
                                  self.get_instances_in_states([self.STATES['shutting-down']],
                                                               selector=selector),
                                  state_code=self.STATES['shutting-down'],
                                  new_state_code=self.STATES['terminated'])

    def _wait_for_stopping_instances(self, instances=None, selector=None):
        self.logger.info("Waiting for stopping instances to stop ....")
        self._wait_for_transition(instances or
                                  self.get_instances_in_states([self.STATES['stopping']],
                                                               selector=selector),
                                  state_code=self.STATES['stopping'],
                                  new_state_code=self.STATES['stopped'])


def print_status(instance_infos):

    if instance_infos is not None:
        color_table = ColorTable('Instance',
                                 'State',
                                 'Public',
                                 'SSHKey',
                                 'SecurityGroups',
                                 'Zone',
                                 'Contact')
        for instance_info in instance_infos:
            color_table.add(Instance="{}|{}".format(instance_info.id, instance_info.name,),
                            State="{}|{}".format(instance_info.state_code, instance_info.state),
                            Public="{}|{}".format(instance_info.public_dns_name,
                                                  instance_info.public_ip_address),
                            SSHKey=instance_info.ssh_key_name,
                            SecurityGroups=", ".join(g.name for g in instance_info.security_groups),
                            Zone=instance_info.placement,
                            Contact=instance_info.owner_email)

        print color_table


def _inverse_lookup(dictionary, value):
    """Does an inverse lookup of key from value"""
    return [key for key in dictionary if dictionary[key] == value]
