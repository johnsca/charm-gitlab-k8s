from ops.framework import Object


class HTTPInterfaceProvides(Object):
    def __init__(self, parent, relation_name):
        super().__init__(parent, relation_name)
        self.relation_name = relation_name

    @property
    def clients(self):
        return []


class HTTPInterfaceClient:
    pass


class MySQLInterfaceRequires(Object):
    def __init__(self, parent, relation_name):
        super().__init__(parent, relation_name)
        self.relation_name = relation_name

    @property
    def _relations(self):
        return self.framework.model.relations[self.relation_name]

    def _field(self, field_name, default=None):
        if not self.is_single:
            return None
        rel = self._relations[0]
        if not rel.app:
            return None
        for candidate in [rel.app] + list(rel.units):
            field_value = rel.data[candidate].get(field_name)
            if field_value:
                return field_value
        return default

    @property
    def is_joined(self):
        return len(self._relations) > 0

    @property
    def is_single(self):
        return len(self._relations) == 1

    @property
    def is_ready(self):
        return self.is_single and all([self.database, self.host, self.username, self.password])

    @property
    def database(self):
        return self._field('database')

    @property
    def host(self):
        return self._field('host')

    @property
    def port(self):
        return int(self._field('port', '3306'))

    @property
    def username(self):
        return self._field('user')

    @property
    def password(self):
        return self._field('password')
