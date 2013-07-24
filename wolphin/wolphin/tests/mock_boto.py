"""Mocks those parts of boto that are needed by wolphin"""

import uuid
import datetime

from boto.exception import EC2ResponseError

STATES = {
    'pending': 0,
    'running': 16,
    'shutting-down': 32,
    'stopping': 64,
    'stopped': 80,
    'terminated': 48
}


def connect_to_region(region,
                      aws_access_key_id=None,
                      aws_secret_access_key=None):
    return MockEC2Connection(aws_access_key_id=aws_access_key_id,
                             aws_secret_access_key=aws_secret_access_key,
                             region=region)


class MockEC2Connection(object):
    def __init__(self,
                 aws_access_key_id,
                 aws_secret_access_key,
                 region=None,
                 custom_instance_update_seq=None):
        self.aws_secret_access_key = aws_secret_access_key
        self.aws_access_key_id = aws_access_key_id
        self.instance_limit = 20
        self.INSTANCES = dict()
        self.custom_instance_update_seq = custom_instance_update_seq

    def get_non_terminated_instances(self):
        instances = []
        for k, v in self.INSTANCES.iteritems():
            if v.state_code != 48:
                instances.append(v)
        return instances

    def run_instances(self,
                      ami_id,
                      min_count=0,
                      max_count=0,
                      key_name=None,
                      security_groups=None,
                      instance_type=None,
                      placement=None):
        if not 1 <= int(min_count) <= int(max_count):
            raise EC2ResponseError(status=400,
                                   reason="InvalidParameters",
                                   body="InvalidParameters: Invalid min_count and max_count "
                                   "arguments")

        non_terminated_count = len(self.get_non_terminated_instances())
        if non_terminated_count + int(min_count) > self.instance_limit:
            if non_terminated_count >= self.instance_limit:
                raise EC2ResponseError(status=400,
                                       reason="InstanceLimitExceeded",
                                       body="InstanceLimitExceeded : {} instances already "
                                       "running".format(non_terminated_count))
            else:
                raise EC2ResponseError(status=400,
                                       reason="InstanceLimitExceeded",
                                       body="InstanceLimitExceeded : Your account allows for "
                                       "only {} more instances"
                                       .format(self.instance_limit - non_terminated_count))
        instances = []

        margin = self.instance_limit - non_terminated_count
        max_count = margin if int(max_count) > margin else int(max_count)
        for x in range(int(max_count)):
            instance = Instance(ami_id,
                                key_name=key_name,
                                security_groups=security_groups,
                                instance_type=instance_type,
                                placement=placement,
                                custom_instance_update_seq=self.custom_instance_update_seq)
            self.INSTANCES[instance.id] = instance
            instances.append(instance)

        return Reservation(instances)

    def create_tags(self, instance_id, tags_dict):
        for k, v in tags_dict.iteritems():
            self.INSTANCES[instance_id].tags[k] = v

    def get_all_instances(self, filters):
        instances = []
        if filters is None:
            instances = self.INSTANCES
        for instance_id, instance in self.INSTANCES.iteritems():
            add_instance = False
            for k, v in filters.iteritems():
                k = k.split(":")[1]
                if k in instance.tags and instance.tags[k] == v:
                    add_instance = True
                    break
            if add_instance:
                instances.append(instance)
        return [Reservation(instances)]


class Group(object):
    def __init__(self, name):
        self.id = uuid.uuid4()
        self.name = name


class Reservation(object):
    def __init__(self, instances):
        self.id = "r-{}".format(uuid.uuid4())
        self.instances = instances


class Instance(object):
    def __init__(self,
                 image_id,
                 key_name,
                 security_groups,
                 instance_type,
                 placement,
                 custom_instance_update_seq=None):

        self.id = "i-{}".format(uuid.uuid4())
        self.public_dns_name = "{}.wolphin.example.com".format(uuid.uuid4())
        self.ip_address = "100.100.100.100"
        self.private_dns_name = "{}.in.example.com".format(uuid.uuid4())
        self.private_ip_address = "1.1.1.1"
        self.image_id = image_id,
        self.key_name = key_name,
        self.groups = []
        for group_name in security_groups:
            self.groups.append(Group(group_name))
        self.instance_type = instance_type
        self.placement = placement
        self.state_code = STATES['pending']
        self.state = 'pending'
        self.tags = dict()
        self.launch_time = str(datetime.datetime.now())
        self.custom_instance_update_seq = custom_instance_update_seq
        self.custom_instance_update_seq_loc = 0

    def start(self):
        if self.state_code != STATES['terminated'] and self.state_code != STATES['running']:
            self.state_code = STATES['pending']
            self.state = 'pending'

    def stop(self):
        if self.state_code != STATES['terminated'] and self.state_code != STATES['stopped']:
            self.state_code = STATES['stopping']
            self.state = 'stopping'

    def terminate(self):
        if self.state_code != STATES['terminated']:
            self.state_code = STATES['shutting-down']
            self.state = 'shutting-down'

    def reboot(self):
        self.start()

    def update(self):
        'Mock changing over from a transitioning to a stable state'

        if self.custom_instance_update_seq is not None:
            # cycle through the custom update sequence every time update is called,
            # if custom update sequence exists.
            index = self.custom_instance_update_seq_loc
            index = 0 if index == len(self.custom_instance_update_seq) else index
            self.state = self.custom_instance_update_seq[index]
            self.state_code = STATES[self.state]
            self.custom_instance_update_seq_loc = index + 1
        elif self.state_code == STATES['pending']:
            self.state_code = STATES['running']
            self.state = 'running'
        elif self.state_code == STATES['stopping']:
            self.state_code = STATES['stopped']
            self.state = 'stopped'
        elif self.state_code == STATES['shutting-down']:
            self.state_code = STATES['terminated']
            self.state = 'terminated'
