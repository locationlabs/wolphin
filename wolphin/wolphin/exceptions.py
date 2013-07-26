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
        return "{}: {}".format(self.__class__.__name__, self.message)


class NoRunningInstances(WolphinException):
    """
    Raised when a project has no running instances.
    """

    def __init__(self, message=None):
        super(NoRunningInstances, self).__init__(message)


class EC2InstanceLimitExceeded(WolphinException):
    """
    Raised when ec2 instance limit is exceeded.
    """

    def __init__(self, message=None):
        super(EC2InstanceLimitExceeded, self).__init__(message)


class InvalidWolphinConfiguration(WolphinException):
    """
    Raised when an invalid wolphin configuration is encountered.
    """

    def __init__(self, message=None):
        super(InvalidWolphinConfiguration, self).__init__(message)
