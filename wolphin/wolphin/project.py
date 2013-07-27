from time import sleep

from boto.exception import EC2ResponseError
from boto.ec2 import connect_to_region
from gusset.colortable import ColorTable

from wolphin.attribute_dict import AttributeDict
from wolphin.exceptions import (InvalidWolphinConfiguration,
                                EC2InstanceLimitExceeded,
                                WolphinException)


class WolphinProject(object):

    def __init__(self, config):

        self.STATES = {
            'pending': 0,
            'running': 16,
            'shutting-down': 32,
            'stopping': 64,
            'stopped': 80,
            'terminated': 48
        }

        valid, err_msg = config.validate()

        if not valid:
            raise InvalidWolphinConfiguration(err_msg)

        self.config = config
        self.conn = connect_to_region(self.config.region,
                                      aws_access_key_id=self.config.aws_access_key_id,
                                      aws_secret_access_key=self.config.aws_secret_key)

    def create(self):
        """
        Creates a new wolphin project and the requested number of ec2 instances for the project
        """

        print "Finding any existing reusable hosts .... "
        # now wait for the shutting-down and stopping instances to finish shutting down / stopping.
        self._wait_for_shutting_down_instances()
        self._wait_for_stopping_instances()

        healthy = self.get_healthy_instances()

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

        if needed_max > 0:
            # boto requires minimum number of instances requested to be 1
            needed_min = 1 if needed_min < 1 else needed_min

            # get the max instance number to start tagging with. Do this before requesting instances
            # so that there is no lag between reservation and tagging.
            instances = self.get_all_instances()
            counter = max(0, *[self._get_instance_number(i) for i in instances]) if instances else 0

            print ("Requesting between {} and {} EC2 instances"
                   " for project: {} ....".format(needed_min, needed_max, self.config.project))

            reservation = self._reserve(needed_min, needed_max)
            provided = len(reservation.instances)
            print ("{} instances provided by Amazon, total being prepared: "
                   "{}".format(provided, provided + already_present))

            # Tagging instances with the project name.
            for instance in reservation.instances:
                counter += 1
                self._tag_instance(instance, counter)
                healthy.append(instance)

        # waiting for all the healthy ones to be running
        print "Waiting for all instances to start ...."
        self._wait_for_transition(healthy, new_state_code=self.STATES['running'])

        print ("{} ec2 instances ready for project "
               "{}".format(len(self.get_instances_in_state(self.STATES['running'])),
                           self.config.project))

        return self.status()

    def start(self, instance_numbers=None):
        """Start the appropriate ec2 instance(s) based on ``self.config``"""

        # wait for the stopping instances to finish stopping as they cannot be started if
        # they are in the middle of stopping.
        self._wait_for_stopping_instances(instance_numbers=instance_numbers)

        # start the instances that are not already running and not pending to start,
        # or not stopped yet.
        instances = self.get_healthy_instances(instance_numbers=instance_numbers)
        for instance in instances:
            if instance.state_code not in [self.STATES['stopping'],
                                           self.STATES['running'],
                                           self.STATES['pending']]:
                instance.start()

        self._wait_for_starting_instances(instances=instances)

        return self.status(instance_numbers=instance_numbers)

    def stop(self, instance_numbers=None):
        """Stop the appropriate ec2 instance(s)"""

        # wait for the starting instances to finish starting as they cannot be stopped if
        # they are in the middle of starting.
        self._wait_for_starting_instances(instance_numbers=instance_numbers)

        # stop the instances that are not already stopping or stopped or pending.
        instances = self.get_healthy_instances(instance_numbers=instance_numbers)

        for instance in instances:
            if instance.state_code not in [self.STATES['pending'],
                                           self.STATES['stopping'],
                                           self.STATES['stopped']]:
                instance.stop()

        self._wait_for_stopping_instances(instances=instances)

        return self.status(instance_numbers=instance_numbers)

    def reboot(self, instance_numbers=None):
        self.stop(instance_numbers=instance_numbers)
        self.start(instance_numbers=instance_numbers)
        return self.status(instance_numbers=instance_numbers)

    def revert(self, sequential=False, instance_numbers=None):
        """
        Given the instances requested to be reverted:
         For each such instance:
          - saves the instance number
          - change the instance number on the one being terminated to <instance number>_terminated
          - run a new instance
          - tag it with this previous instance number.
        """

        print "Starting reverting ....",
        instances = self.get_healthy_instances(instance_numbers=instance_numbers)
        print len(instances), "instances ..",
        if sequential:
            print "sequentially ...."
            for instance in instances:
                instance_number = self._get_instance_number(instance)
                self._tag_instance(instance, "{}_terminated".format(instance_number))
                instance.terminate()
                self._wait_for_transition([instance, ],
                                          state_code=self.STATES['shutting-down'],
                                          new_state_code=self.STATES['terminated'])
                print "Getting a new instance ...."
                reservation = self._reserve(1, 1)
                instances = reservation.instances
                print len(instances), "received from Amazon."
                self._tag_instance(instances[0], instance_number)
                self._wait_for_transition(instances, state_code=self.STATES['pending'],
                                          new_state_code=self.STATES['running'])

        else:
            print "in a batch ...."
            instance_numbers = []
            for instance in instances:
                instance_number = self._get_instance_number(instance)
                instance_numbers.append(instance_number)
                self._tag_instance(instance, "{}_terminated".format(instance_number))
                instance.terminate()
            self._wait_for_transition(instances,
                                      state_code=self.STATES['shutting-down'],
                                      new_state_code=self.STATES['terminated'])

            instances_needed = len(instance_numbers)
            print "Getting {} new instances {} ....".format(instances_needed, instance_numbers)
            if instances_needed > 0:
                reservation = self._reserve(instances_needed, instances_needed)
                instances = reservation.instances
                print len(instances), "received from Amazon."
                counter = 0
                for instance_number in instance_numbers:
                    self._tag_instance(instances[counter], instance_number)
                    counter += 1
                self._wait_for_transition(instances,
                                          state_code=self.STATES['pending'],
                                          new_state_code=self.STATES['running'])

        return self.status(instance_numbers=instance_numbers)

    def status(self, instances=None, instance_numbers=None):
        """Returns the statuses of requested wolphin project instances"""
        status_info = []
        if instances is None:
            instances = self._select_instances(instance_numbers=instance_numbers)

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

    def terminate(self, instance_numbers=None):
        """Terminate instances"""
        instances = self.get_healthy_instances(instance_numbers=instance_numbers)
        for instance in instances:
            if "terminated" not in self._get_instance_suffix(instance):
                self._tag_instance(instance,
                                   "{}_terminated".format(self._get_instance_number(instance)))
                instance.terminate()

        self._wait_for_shutting_down_instances(instances)

        return self.status(instance_numbers=instance_numbers)

    def get_healthy_instances(self, instance_numbers=None):
        """
        Returns instances that are not terminated and not going towards termination (shutting-down).
        """

        return [i for i in self._select_instances(instance_numbers=instance_numbers)
                if i.state_code not in [self.STATES['terminated'], self.STATES['shutting-down']]]

    def get_instances_in_state(self, state_code, instance_numbers=None):
        """Returns project instances that are in the given ``state_code``"""
        if state_code not in self.STATES.itervalues():
            return []
        return [i for i in self._select_instances(instance_numbers=instance_numbers)
                if i.state_code == state_code]

    def get_instances(self, instance_name_suffix):
        """Gets the ec2 instance(s) by its wolphin project instance name"""

        reservations = self.conn.get_all_instances(filters={"tag:Name":
                                                            "wolphin."
                                                            "{}.{}".format(self.config.project,
                                                                           instance_name_suffix)})

        return self._get_instances_from_reservations(reservations)

    def get_all_instances(self):
        """Get all instances for a wolphin project on ec2"""

        reservations = self.conn.get_all_instances(filters={"tag:ProjectName":
                                                            "wolphin."
                                                            "{}".format(self.config.project)})

        return self._get_instances_from_reservations(reservations)

    def _get_instance_suffix(self, instance):
        """Returns the instance suffix for the ``instance``"""

        return str((instance).tags.get("Name")).split(".")[-1]

    def _get_instance_number(self, instance):
        """Parses the instance name to get the instance number"""

        suffix = self._get_instance_suffix(instance)
        return int(suffix.split("_")[0])

    def _get_instances_from_reservations(self, reservations):
        """Flatten all reservations to get one instances list"""

        instances = [i for reservation in reservations or [] for i in reservation.instances]

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

    def _select_instances(self, instance_numbers=None):
        """gets the instances based on the self.config"""

        instances = []

        # see if only a specific host's status is needed
        if instance_numbers:
            for instance_number in instance_numbers:
                got_instances = self.get_instances(instance_number)
                if got_instances:
                    for instance in got_instances:
                        instances.append(instance)
        else:
            # if no single host specified then get by the project
            instances = self.get_all_instances()
        return instances

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

    def _wait_for_starting_instances(self, instances=None, instance_numbers=None):
        print "Waiting for pending instances to start ...."
        self._wait_for_transition(instances or
                                  self.get_instances_in_state(self.STATES['pending'],
                                                              instance_numbers=instance_numbers),
                                  state_code=self.STATES['pending'],
                                  new_state_code=self.STATES['running'])

    def _wait_for_shutting_down_instances(self, instances=None, instance_numbers=None):
        print "Waiting for shutting-down instances to terminate ...."
        self._wait_for_transition(instances or
                                  self.get_instances_in_state(self.STATES['shutting-down'],
                                                              instance_numbers=instance_numbers),
                                  state_code=self.STATES['shutting-down'],
                                  new_state_code=self.STATES['terminated'])

    def _wait_for_stopping_instances(self, instances=None, instance_numbers=None):
        print "Waiting for stopping instances to stop ...."
        self._wait_for_transition(instances or
                                  self.get_instances_in_state(self.STATES['stopping'],
                                                              instance_numbers=instance_numbers),
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
