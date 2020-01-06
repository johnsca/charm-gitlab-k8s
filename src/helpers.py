from ops.framework import Object


class Part(Object):
    def __init__(self, parent=None, key=None):
        if parent:
            super().__init__(parent, key)
            self.name = key
        else:
            self.name = None

    def __set_name__(self, parent_type, name):
        self.name = name

    def __get__(self, parent, parent_type):
        if parent:
            bound = type(self)(parent, self.name)
            setattr(parent, self.name, bound)
            return bound
        else:
            return self
