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
    def __init__(self, message=None):
        """
        WolphinException constructor

        :param message: error message for the exception
        """

        super(NoRunningInstances, self).__init__(err_msg("No Running Instances found{}",
                                                         message))


class EC2InstanceLimitExceeded(WolphinException):
    """
    Raised when ec2 instance limit is exceeded.
    """

    def __init__(self, message=None):

        super(EC2InstanceLimitExceeded, self).__init__(err_msg("EC2 instance limit exceeded{}",
                                                               message))


class InvalidWolphinConfiguration(WolphinException):
    """
    Raised when an invalid wolphin configuration is encountered.
    """

    def __init__(self, message=None):

        super(InvalidWolphinConfiguration, self).__init__(err_msg("Invalid Wolphin Configuration{}",
                                                                  message))


def err_msg(base, extension=None):
    message = ": {}".format(extension) if extension is not None else ""
    return base.format(message)
