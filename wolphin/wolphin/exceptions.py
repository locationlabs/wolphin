class WolphinException(Exception):
    """
    Base class for wolphin related exceptions
    """
    def __init__(self, message=None):
        """
        WolphinException constructor

        :param message: error message for the exception
        """

        self.message = message

    def __str__(self):
        return self.message


class NoRunningInstances(WolphinException):
    """
    Raised when a project has no running instances.
    """

    pass


class EC2InstanceLimitExceeded(WolphinException):
    """
    Raised when ec2 instance limit is exceeded.
    """

    pass


class InvalidWolphinConfiguration(WolphinException):
    """
    Raised when an invalid wolphin configuration is encountered.
    """

    pass
