class AttributeDict(dict):
    """
    A simple class to dynamically add attributes.
    """

    def __init__(self, *args, **kwargs):
        super(AttributeDict, self).__init__(*args, **kwargs)
        self.__dict__ = self
