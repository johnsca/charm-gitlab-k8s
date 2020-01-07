#!/usr/bin/env python3

import sys
sys.path.append('lib')

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    WaitingStatus,
    MaintenanceStatus,
)

from interfaces import (
    HTTPInterfaceProvides,
    MySQLInterfaceRequires,
)
from resources import OCIImageResource


class GitLabK8sCharm(CharmBase):
    state = StoredState()

    def __init__(self, framework, key):
        super().__init__(framework, key)

        for event in (self.on.start,
                      self.on.upgrade_charm,
                      self.on.config_changed,
                      self.on.mysql_relation_changed):
            self.framework.observe(event, self.on_start)
        self.framework.observe(self.on.website_relation_joined, self)

        self.website = HTTPInterfaceProvides('website')
        self.mysql = MySQLInterfaceRequires('mysql')
        self.gitlab_image = OCIImageResource('gitlab_image')


    def on_install(self, event):
        self.state.is_started = False

    def on_start(self, event):
        unit = self.framework.model.unit
        if not self.gitlab_image.fetch():
            unit.status = BlockedStatus('Missing or invalid image resource')
            return
        if not self.mysql.is_joined:
            unit.status = BlockedStatus('Missing database')
        if not self.mysql.is_single:
            unit.status = BlockedStatus('Too many databases')
        if not self.mysql.is_ready:
            unit.status = WaitingStatus('Waiting for database')
            return
        if not self.framework.model.unit.is_leader():
            unit.status = WaitingStatus('Not leader')
            return
        unit.status = MaintenanceStatus('Configuring container')
        self.framework.model.pod.set_spec({
            'containers': [{
                'name': self.framework.model.app.name,
                'imageDetails': {
                    'imagePath': self.gitlab_image.registry_path,
                    'username': self.gitlab_image.username,
                    'password': self.gitlab_image.password,
                },
                'ports': [{
                    'containerPort': int(self.framework.model.config['http_port']),
                    'protocol': 'TCP',
                }],
                'config': {
                    'GITLAB_OMNIBUS_CONFIG': '; '.join([
                        f"postgresql['enable'] = false",  # disable DB included in image
                        f"gitlab_rails['db_adapter'] = 'mysql2'",
                        f"gitlab_rails['db_encoding'] = 'utf8'",
                        f"gitlab_rails['db_database'] = '{self.mysql.database}'",
                        f"gitlab_rails['db_host'] = '{self.mysql.host}'",
                        f"gitlab_rails['db_port'] = {self.mysql.port}",
                        f"gitlab_rails['db_username'] = '{self.mysql.username}'",
                        f"gitlab_rails['db_password'] = '{self.mysql.password}'",
                    ]),
                }
            }],
        })
        self.state.is_started = True
        unit.status = ActiveStatus()

    def on_website_relation_joined(self, event):
        if not self.state.is_started:
            event.defer()
            return

        self.config = self.framework.model.config
        for client in self.website.clients:
            client.serve(hosts=[client.ingress_address],
                         port=self.config['http_port'])


if __name__ == '__main__':
    main(GitLabK8sCharm)
