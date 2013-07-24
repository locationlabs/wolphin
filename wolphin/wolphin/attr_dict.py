class AttrDict(dict):
    """
    A simple AttrDict class to dynamically add attributes.
    """

    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self
