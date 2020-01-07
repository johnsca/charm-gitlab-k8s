from pathlib import Path

import yaml
from ops.framework import Object
from ops.model import ModelError


class OCIImageResource(Object):
    def __init__(self, parent, resource_name):
        super().__init__(parent, resource_name)
        self.resource_name = resource_name
        self.registry_path = None
        self.username = None
        self.password = None

    def fetch(self):
        try:
            resource_path = self.framework.model.resources.fetch(self.resource_name)
        except ModelError:
            raise
        resource_text = Path(resource_path).read_text()
        if not resource_text:
            raise ValueError('empty yaml')
        try:
            resource_data = yaml.safe_load(resource_text)
        except yaml.YAMLError:
            raise ValueError(f'invalid yaml: {resource_text}')
        else:
            self.registry_path = resource_data['registrypath']
            self.username = resource_data['username']
            self.password = resource_data['password']
            return True
