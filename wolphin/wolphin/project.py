from time import sleep

from boto.exception import EC2ResponseError
from boto.ec2 import connect_to_region
from gusset.colortable import ColorTable

from wolphin.attribute_dict import AttributeDict
from wolphin.exceptions import EC2InstanceLimitExceeded, WolphinException
from wolphin.selector import DefaultSelector


class WolphinProject(object):

    def __init__(self, selector=None):
        self.STATES = {
            'pending': 0,
            'running': 16,
            'shutting-down': 32,
            'stopping': 64,
            'stopped': 80,
            'terminated': 48
        }

        self.instance_selector = selector or DefaultSelector()

    @classmethod
    def new(cls, config, selector=None):
        """
        Factory method to create a new instance of WolphinProject.

        :param config: `class:wolphin.config.Configuration` object to configure the project with.
        :returns: `class:wolphin.project.WolphinProject`.
        """

        config.validate()
        project = cls(selector=selector)
        project.config = config
        project.conn = connect_to_region(project.config.region,
                                         aws_access_key_id=project.config.aws_access_key_id,
                                         aws_secret_access_key=project.config.aws_secret_key)
        return project

    def create(self):
        """
        Creates a new wolphin project and the requested number of ec2 instances for the project
        """

        print "Finding any existing reusable hosts .... "
        # now wait for the shutting-down and stopping instances to finish shutting down / stopping.
        self._wait_for_shutting_down_instances(bypass_selector=True)
        self._wait_for_stopping_instances(bypass_selector=True)

        healthy = self.get_healthy_instances(bypass_selector=True)

        # see how many extra need to be requested or if any existing ones need to be terminated.
        already_present = len(healthy)
        needed_min = needed_max = 0

        # terminate some extra instances if already present healthy instances are more than needed.
        if already_present > int(self.config.max_instance_count):
            for _ in range(already_present - int(self.config.max_instance_count)):
                instance = healthy.pop()
                instance.terminate()
            self._wait_for_shutting_down_instances()

        # if more are needed, compute the range.
        elif already_present < int(self.config.min_instance_count):
            needed_min = int(self.config.min_instance_count) - already_present
            needed_max = int(self.config.max_instance_count) - already_present
        elif (int(self.config.min_instance_count) <= already_present and
              already_present <= int(self.config.max_instance_count)):
            needed_max = int(self.config.max_instance_count) - already_present

        print "More needed from Amazon: between", needed_min, "and", needed_max, "instances"

        # restarting the healthy instances
        for instance in healthy:
            try:
                instance.reboot()
            except EC2ResponseError:
                instance.start()

        if needed_max:
            # boto requires minimum number of instances requested to be 1
            needed_min = max(1, needed_min)

            # get the max instance number to start tagging with. Do this before requesting instances
            # so that there is no lag between reservation and tagging.
            instance_allocation_number = self._max_allocated_number()

            print ("Requesting between {} and {} EC2 instances ....".format(needed_min, needed_max))

            reservation = self._reserve(needed_min, needed_max)
            provided = len(reservation.instances)
            print ("{} instances provided by Amazon, total being prepared: {}"
                   .format(provided, provided + already_present))

            # Tagging instances with the project name.
            for instance in reservation.instances:
                instance_allocation_number += 1
                self._tag_instance(instance, instance_allocation_number)
                healthy.append(instance)

        # waiting for all the healthy ones to be running
        print "Waiting for all instances to start ...."
        self._wait_for_transition(healthy, new_state_code=self.STATES['running'])

        print ("{} ec2 instances ready for project {}"
               .format(len(self.get_instances_in_states([self.STATES['running']])),
                       self.config.project))

        return self.status(bypass_selector=True)

    def _max_allocated_number(self):
        """Returns the maximum instance number allocated to this project's ec2 instances"""
        instances = self.get_all_instances()
        return (max(0, *[self._get_instance_number(instance) for instance in instances])
                if instances else 0)

    def start(self):
        """Start the appropriate ec2 instance(s) based on ``self.config``"""

        # wait for the stopping instances to finish stopping as they cannot be started if
        # they are in the middle of stopping.
        self._wait_for_stopping_instances()

        # start the instances that are not already running, pending to start, or stopping.
        instances = self.get_instances_in_states([self.STATES['shutting-down'],
                                                  self.STATES['terminated'],
                                                  self.STATES['stopping'],
                                                  self.STATES['pending'],
                                                  self.STATES['running']],
                                                 inverse_select=True)
        for instance in instances:
            instance.start()

        self._wait_for_starting_instances(instances=instances)

        return self.status()

    def stop(self):
        """Stop the appropriate ec2 instance(s)"""

        # wait for the starting instances to finish starting as they cannot be stopped if
        # they are in the middle of starting.
        self._wait_for_starting_instances()

        # stop the instances that are not already stopping, stopped or pending.
        instances = self.get_instances_in_states([self.STATES['shutting-down'],
                                                  self.STATES['terminated'],
                                                  self.STATES['pending'],
                                                  self.STATES['stopping'],
                                                  self.STATES['stopped']],
                                                 inverse_select=True)
        for instance in instances:
            instance.stop()

        self._wait_for_stopping_instances(instances=instances)

        return self.status()

    def reboot(self):
        self.stop()
        self.start()
        return self.status()

    def revert(self, sequential=False):
        """Revert project instances"""

        print "Starting reverting ....",
        instances = self.get_healthy_instances()
        print len(instances), "instances ..",
        if instances and sequential:
            print "sequentially ...."
            for instance in instances:
                self._revert([instance])

        elif instances:
            print "in a batch ...."
            self._revert(instances)

        return self.status()

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
        print "Getting a new reservation ...."
        if instance_numbers:
            new_instances = self._reserve(len(instance_numbers), len(instance_numbers)).instances
            print len(new_instances), "received from Amazon."
            counter = 0
            for instance_number in instance_numbers:
                self._tag_instance(new_instances[counter], instance_number)
                counter += 1
            self._wait_for_starting_instances(instances=new_instances)

    def status(self, instances=None, bypass_selector=False):
        """Returns the statuses of requested wolphin project instances"""
        status_info = []
        if instances is None:
            instances = self._select_instances(bypass_selector=bypass_selector)

        if instances:
            for instance in instances:
                status_info.append(AttributeDict(id=instance.id,
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
        return status_info

    def terminate(self, instances=None, force=False):
        """
        Terminate instances

        :param instances: a list of instances to terminate.
        :param force: if True, terminates all instances irrespective of any selectors applied.

        """
        instances_to_terminate = instances or self.get_healthy_instances(bypass_selector=force)
        for instance in instances_to_terminate:
            instance.terminate()

        self._wait_for_shutting_down_instances(instances_to_terminate)

        return self.status(instances=instances_to_terminate)

    def get_healthy_instances(self, bypass_selector=False):
        """
        Returns instances that are not terminated and not going towards termination (shutting-down).
        """

        return self.get_instances_in_states([self.STATES['terminated'],
                                             self.STATES['shutting-down']],
                                            inverse_select=True,
                                            bypass_selector=bypass_selector)

    def get_instances_in_states(self, state_codes, inverse_select=False, bypass_selector=False):
        """Returns project instances that are in the given ``state_codes``"""

        not_in_state = lambda instance: instance.state_code not in state_codes
        in_state = lambda instance: instance.state_code in state_codes
        filter_function = not_in_state if inverse_select else in_state
        instances = self._select_instances(bypass_selector=bypass_selector)

        return filter(filter_function, instances)

    def get_all_instances(self):
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

    def _reserve(self, needed_min=None, needed_max=None):
        """
        Makes a reservation for ec2 instances, on amazon ec2, based on ``self.config`` parameters,
        starts the instances and returns the reservation.
        """

        needed_min = needed_min or self.config.min_instance_count
        needed_max = needed_max or self.config.max_instance_count

        # reserve and run instances.
        try:
            reservation = self.conn.run_instances(self.config.ami_id,
                                                  min_count=str(needed_min),
                                                  max_count=str(needed_max),
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

    def _select_instances(self, bypass_selector=False):
        """Gets the instances based on self.config"""

        all_instances = self.get_all_instances()
        return all_instances if bypass_selector else self.instance_selector.select(all_instances)

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

        max_tries = int(self.config.max_wait_tries)
        refresh_rate = int(self.config.max_wait_duration)

        if not instances:
            return
        for attempt in range(max_tries):
            instance_count = len(instances)
            print ("Waiting for {} instances to go from {} to {} (refreshed every {} secs., "
                   "max {} secs.)".format(instance_count,
                                          _inverse_lookup(self.STATES, state_code),
                                          _inverse_lookup(self.STATES, new_state_code),
                                          refresh_rate,
                                          max_tries * refresh_rate))

            keep_waiting = False
            color_table = ColorTable('instance', 'state')
            for instance in instances:
                instance.update()
                color_table.add(instance="{}|{}".format(instance.id, instance.tags.get("Name")),
                                state="{}|{}".format(instance.state_code, instance.state))

                if ((state_code is not None and instance.state_code == state_code) or
                        (new_state_code is not None and instance.state_code != new_state_code)):
                    keep_waiting = True

            print color_table
            if not keep_waiting:
                break
            if attempt == max_tries - 1:
                print "!! Max amount of wait reached, will not wait anymore, continuing ...."
            else:
                sleep(refresh_rate)

        return instances

    def _wait_for_starting_instances(self, instances=None):
        print "Waiting for pending instances to start ...."
        self._wait_for_transition(instances or
                                  self.get_instances_in_states([self.STATES['pending']]),
                                  state_code=self.STATES['pending'],
                                  new_state_code=self.STATES['running'])

    def _wait_for_shutting_down_instances(self, instances=None, bypass_selector=False):
        print "Waiting for shutting-down instances to terminate ...."
        self._wait_for_transition(instances or
                                  self.get_instances_in_states([self.STATES['shutting-down']],
                                                               bypass_selector=bypass_selector),
                                  state_code=self.STATES['shutting-down'],
                                  new_state_code=self.STATES['terminated'])

    def _wait_for_stopping_instances(self, instances=None, bypass_selector=False):
        print "Waiting for stopping instances to stop ...."
        self._wait_for_transition(instances or
                                  self.get_instances_in_states([self.STATES['stopping']],
                                                               bypass_selector=bypass_selector),
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
