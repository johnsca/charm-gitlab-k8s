from pathlib import Path

import yaml
from ops.model import ModelError

from helpers import Part


class OCIImageResource(Part):
    registry_path = None
    username = None
    password = None

    def fetch(self):
        try:
            resource_path = self.framework.model.resources.fetch(self.name)
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
