""" The defaults used by wolphin """

# A suitable AMI - a suggested ubuntu AMI listed here. Don't forget to find the right ID for
# your region.
AMI_ID = 'ami-87712ac2'

# Should match the AMI - I do not recommend using micros for live tests
# but it's useful for dev work.
INSTANCE_TYPE = 't1.micro'

# Should match the AMI
USER = 'ubuntu'

# The name of *your* security group in *your* Amazon account
INSTANCE_SECURITYGROUP = 'default'

# Specify the region you will be working in. Required so that we can find the right ami in the
# right availability zone.
REGION = 'us-west-1'

# Should match the AMI and be available in the region above.
INSTANCE_AVAILABILITYZONE = 'us-west-1b'

# Min Number of instances to be spawned
MIN_INSTANCE_COUNT = 1

# Max number of instances to be spawned
MAX_INSTANCE_COUNT = 7

# Maximum duration in seconds for which to wait each time when waiting for state transitions
MAX_WAIT_DURATION = 5

# Maximum number of times to wait when waiting for state transitions
MAX_WAIT_TRIES = 12
