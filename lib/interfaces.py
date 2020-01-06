from helpers import Part


class HTTPInterfaceProvides(Part):
    @property
    def clients(self):
        return []


class HTTPInterfaceClient:
    pass


class MySQLInterfaceRequires(Part):
    @property
    def _relations(self):
        return self.framework.model.relations[self.name]

    def _field(self, field_name):
        if not self.is_single:
            return None
        rel = self._relations[0]
        if not rel.app:
            return None
        for candidate in [rel.app] + list(rel.units):
            field_value = rel.data[candidate].get(field_name)
            if field_value:
                return field_value
        return None

    @property
    def is_joined(self):
        return len(self._relations) > 0

    @property
    def is_single(self):
        return len(self._relations) == 1

    @property
    def is_ready(self):
        return all([self.database, self.host, self.username, self.password])

    @property
    def database(self):
        return self._field('database')

    @property
    def host(self):
        return self._field('host')

    @property
    def username(self):
        return self._field('username')

    @property
    def password(self):
        return self._field('password')
