#!/usr/bin/env python3

import sys
sys.path.append('lib')

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    ModelError,
    WaitingStatus,
)

from interface_http import HTTPServer
from interface_mysql import MySQLServer, MySQLServerError
from oci_image import OCIImageResource


class GitLabK8sCharm(CharmBase):
    state = StoredState()

    def __init__(self, framework, key):
        super().__init__(framework, key)

        self.website = HTTPServer(self, 'website')
        self.mysql = MySQLServer(self, 'mysql')
        self.gitlab_image = OCIImageResource(self, 'gitlab_image')

        self.state.is_started = getattr(self.state, 'is_started', False)

        self.framework.observe(self.on.start, self.update_status)
        self.framework.observe(self.on.update_status, self.update_status)
        self.framework.observe(self.mysql.on.database_available, self.configure_container)
        self.framework.observe(self.mysql.on.database_changed, self.configure_container)
        self.framework.observe(self.on.website_relation_joined, self)

    def update_status(self, event):
        try:
            db = self.mysql.database()
        except MySQLServerError as e:
            self.model.unit.status = e.status
        else:
            if not self.model.unit.is_leader():
                self.model.unit.status = WaitingStatus('Not leader')

    def configure_container(self, event):
        if not self.model.unit.is_leader():
            self.model.unit.status = WaitingStatus('Not leader')
            return
        try:
            self.gitlab_image.fetch()
        except (ModelError, ValueError) as e:
            self.model.unit.status = BlockedStatus(f'Unable to fetch image resource: {e}')
            return
        db = self.mysql.database()
        self.model.pod.set_spec({
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
                        f"gitlab_rails['db_database'] = '{db.name}'",
                        f"gitlab_rails['db_host'] = '{db.host}'",
                        f"gitlab_rails['db_port'] = {db.port}",
                        f"gitlab_rails['db_username'] = '{db.username}'",
                        f"gitlab_rails['db_password'] = '{db.password}'",
                    ]),
                }
            }],
        })
        self.state.is_started = True
        self.model.unit.status = ActiveStatus()

    def on_website_relation_joined(self, event):
        if not self.state.is_started:
            event.defer()
            return

        for client in self.website.clients:
            client.serve(hosts=[client.ingress_address],
                         port=self.model.config['http_port'])


if __name__ == '__main__':
    main(GitLabK8sCharm)
