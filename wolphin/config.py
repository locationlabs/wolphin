from os.path import expanduser, abspath, exists, join
import re

from wolphin.exceptions import InvalidWolphinConfiguration


class Configuration(object):
    """Configuration for any Wolphin project"""

    DEFAULT_REGION = 'us-west-1'
    DEFAULT_AMI_ID = 'ami-87712ac2'
    DEFAULT_INSTANCE_TYPE = 't1.micro'
    DEFAULT_USER = 'ubuntu'
    DEFAULT_INSTANCE_AVAILABILITYZONE = 'us-west-1b'
    DEFAULT_SECURITYGROUP = 'default'

    DEFAULT_MIN_INSTANCE_COUNT = 1
    DEFAULT_MAX_INSTANCE_COUNT = 1

    DEFAULT_MAX_WAIT_TRIES = 12
    DEFAULT_MAX_WAIT_DURATION = 10

    def __init__(self,
                 project=None,
                 email=None,
                 region=DEFAULT_REGION,
                 ami_id=DEFAULT_AMI_ID,
                 instance_type=DEFAULT_INSTANCE_TYPE,
                 user=DEFAULT_USER,
                 instance_availabilityzone=DEFAULT_INSTANCE_AVAILABILITYZONE,
                 instance_securitygroup=DEFAULT_SECURITYGROUP,
                 min_instance_count=DEFAULT_MIN_INSTANCE_COUNT,
                 max_instance_count=DEFAULT_MAX_INSTANCE_COUNT,
                 amazon_keypair_name=None,
                 pem_file=None,
                 pem_path=None,
                 aws_access_key_id=None,
                 aws_secret_key=None,
                 max_wait_tries=DEFAULT_MAX_WAIT_TRIES,
                 max_wait_duration=DEFAULT_MAX_WAIT_DURATION):
        """
        Initialize a wolphin configuration from defaults and any provided parameters.

        :param project: wolphin project name.
        :param email: email address of the project owner.
        :param region: region to spawn the ec2 instances in.
        :param ami_id: a suitable AMI Id (Amazon Machine Instance Id) of the base image to be used.
         Don't forget to find the right ID for your region.
        :param instance_type: ec2 isntance type, should match the AMI.
        :param user: a valid account username which can access the ec2 instances, should match
         the AMI.
        :param instance_availabilityzone: the zone to make the ec2 instances available in.
        :param instance_securitygroup: the security group for the ec2 instances, this should be
         the name of *your* security group in *your* Amazon account.
        :param min_instance_count: minimum number of ec2 instances to request.
        :param max_instance_count maximum number of ec2 instances to request.
        :param amazon_keypair_name: the key pair name in use for ec2 instances.
        :param pem_file: name of the .pem file.
        :param pem_path: path to the .pem file.
        :param aws_access_key_id: amazon web services access key id.
        :param aws_secret_key: amazon web services secret key.
        :param max_wait_tries: maximum number of retries to make.
        :param max_wait_duration: maximum duration in seconds, to wait during instance state
         transition, for each try.
        """

        self.project = project
        self.email = email
        self.region = region
        self.ami_id = ami_id
        self.instance_type = instance_type
        self.user = user
        self.instance_availabilityzone = instance_availabilityzone
        self.instance_securitygroup = instance_securitygroup
        self.min_instance_count = min_instance_count
        self.max_instance_count = max_instance_count
        self.amazon_keypair_name = amazon_keypair_name
        self.pem_file = pem_file
        self.pem_path = pem_path
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_key = aws_secret_key
        self.max_wait_tries = max_wait_tries
        self.max_wait_duration = max_wait_duration

    @classmethod
    def create(cls, *config_files):
        """
        Factory Method to create a config from ``config_files``.

        :param config_files: files containing overrides for config.
        """

        config = cls()
        for config_file in config_files:
            config.parse_config_file(config_file)

        return config

    def parse_config_file(self, property_file):
        """
        Reads the ``property_file`` to extract properties and updates the ``config`` with them.

        The format of properties should be:
            k = v or k = "v" or k = 'v'

        All comments (anything after a '#') are ignored from the ``property_file``. Moreover, all
        comments should be on a separate line and not as a continuation of the property, e.g.:
            k = v # comment  - is not considered valid.

        :param property_file: the file containing the properties to overrife the ``config`` with.
        """

        _unquote = lambda word: (word[1:-1]
                                 if ((word.startswith('"') and word.endswith('"')) or
                                     (word.startswith("'") and word.endswith("'")))
                                 else word)

        _as_dict = lambda lines: (dict(map(lambda x: _unquote(x.strip()), l.split('='))
                                  for l in lines if not l.startswith("#") and "=" in l))
        if property_file:
            self.__dict__.update(_as_dict(property_file))

        # convert the values that must be numeric from string to int.
        for integer_attribute in ['min_instance_count',
                                  'max_instance_count',
                                  'max_wait_tries',
                                  'max_wait_duration']:
            setattr(self, integer_attribute, int(getattr(self, integer_attribute)))

    @property
    def ssh_key_file(self):
        """returns the absolute location (with the filename) of the configured .pem file."""
        return abspath(expanduser(join(self.pem_path, self.pem_file)))

    def update(self, **kwargs):
        for key, value in kwargs.iteritems():
            setattr(self, key, value)

    def validate(self):
        """Validates this configuration object"""

        for k, v in self.__dict__.iteritems():
            if not v:
                raise InvalidWolphinConfiguration("{} is missing or None.".format(k))

        # some basic email validation.
        if not re.compile(".+@.+[.].+").match(self.email):
            raise InvalidWolphinConfiguration("email: '{}' is not valid.".format(self.email))

        # min and max instance count validation.
        if not 0 < self.min_instance_count <= self.max_instance_count:
            raise InvalidWolphinConfiguration("min_instance_count and max_instance_count should be"
                                              " such that 0 < min_instance_count <="
                                              " max_instance_count.")

        # is the .pem available?
        if not exists(self.ssh_key_file):
            raise InvalidWolphinConfiguration(".pem file {} could not be found."
                                              .format(self.ssh_key_file))
