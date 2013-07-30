from abc import ABCMeta, abstractmethod


class Selector(object):
    """
    Abstract Selector class.
    """

    __metaclass__ = ABCMeta

    @abstractmethod
    def select(self, instances):
        """
        The function called by WolphinProject to get a list of instances to work with.

        :param instances: the list of all available instances.
        :returns: a filtered/selected list of instances.
        """

        pass


class DefaultSelector(Selector):

    def select(self, instances):
        return instances


class InstanceNumberBasedSelector(Selector):
    def __init__(self, instance_numbers=None):
        self.instance_numbers = [int(number) for number in instance_numbers or []]

    def select(self, instances):
        return ([instance
                for instance in instances or []
                if int(str((instance).tags.get("Name")).split(".")[-1]) in self.instance_numbers]
                if self.instance_numbers else instances)
