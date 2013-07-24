from wolphin import defaults

from os.path import expanduser, abspath, exists, join
import re


def configuration(auth_credentials_file=None,
                  project=None,
                  email=None,
                  user_config_file=None):
    """
    Create a config dict from the defaults, auth_credentials_file as well as user_config_file
    """

    config = dict()

    # Loading defaults into config.
    config.update(defaults.__dict__)

    # Reading the access key file.
    if auth_credentials_file is not None:
        _parse_property_file(config, auth_credentials_file)

    # Overriding / adding any ec2 properties from the provided config file.
    if user_config_file is not None:
        _parse_property_file(config, user_config_file)

    # Overriding the EMAIL property.
    if email is not None:
        config['EMAIL'] = email

    # Overriding the project name.
    if project is not None:
        config['PROJECT'] = project

    return config


def _parse_property_file(dictionary, property_file):
    """
    Reads the ``property_file`` to extract properties and save them in the ``dictionary``.
    The format of properties should be:
        K = V or K = "V" or K = 'V'
    The dictionary would eventually contain:
        K = V for all the properties defined in the ``property_file``
    all comments (anything after a '#') are ignored from the ``property_file``.

    """

    for line in property_file:
        property_pair = line.split("#", 1)[0].strip().split("=", 1)
        if len(property_pair) > 1:
            k = property_pair[0].strip()
            v = property_pair[1].strip()
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                # removing enclosing quotes.
                v = v[1:-1]
            dictionary[k] = v


def validate(config, attributes=None):
    """Validates config"""

    if attributes is None:
        attributes_to_check = {
            'PROJECT': 'wolphin project name',
            'EMAIL': 'email of the project owner',
            'REGION': 'region to spawn the ec2 instances in',
            'AMI_ID': 'Amazon Machine Instance Id - the base machine image to be used',
            'INSTANCE_TYPE': 'ec2 isntance type',
            'USER': 'a valid account username which can access the ec2 instances (AMI)',
            'INSTANCE_AVAILABILITYZONE': 'the zone to make the ec2 instances available in',
            'INSTANCE_SECURITYGROUP': 'the security group for the ec2 instances',
            'MIN_INSTANCE_COUNT': 'minimum number of ec2 instances to request',
            'MAX_INSTANCE_COUNT': 'maximum number of ec2 instances to request',
            'AMAZON_KEYPAIR_NAME': 'the key pair name in use for ec2 instances',
            'PEM_FILE': 'name of the .pem file',
            'PEM_PATH': 'path to the pem file',
            'AWS_ACCESS_KEY_ID': 'Amazon Web Services access key id',
            'AWS_SECRET_KEY': 'Amazon Web Services secret key',
            'MAX_WAIT_TRIES': 'Maximum number of retries to make',
            'MAX_WAIT_DURATION': 'Maximum duration in seconds, \
                                  to wait during instance state transition, for each try.'
        }
    else:
        attributes_to_check = attributes

    for k, v in attributes_to_check.iteritems():
        if k not in config or config[k] is None or 0 == len(str(config[k])):
            return False, "{}({}) is missing or None.".format(k, v)

    if 'EMAIL' in attributes_to_check:
        if not re.compile("[^@]+@[^@]+\.[^@]+").match(config['EMAIL']):
            return False, "EMAIL: '{}' is not valid".format(config['EMAIL'])

    if 'MIN_INSTANCE_COUNT' in attributes_to_check and 'MAX_INSTANCE_COUNT' in attributes_to_check:
        if not 0 < int(config['MIN_INSTANCE_COUNT']) <= int(config['MAX_INSTANCE_COUNT']):
            return False, "MIN_INSTANCE_COUNT and MAX_INSTANCE_COUNT should be such that "\
                          " 0 < MIN_INSTANCE_COUNT <= MAX_INSTANCE_COUNT"

    if 'PEM_PATH' in attributes_to_check and 'PEM_FILE' in attributes_to_check:
        pem_path = join(config['PEM_PATH'], config['PEM_FILE'])
        if not exists(abspath(expanduser(pem_path))):
            return False, ".pem file {} could not be found".format(pem_path)

    return True, "valid"
