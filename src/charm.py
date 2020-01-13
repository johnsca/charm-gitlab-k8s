#!/usr/bin/env python3

import sys
sys.path.append('lib')

from ops.charm import CharmBase, CharmEvents
from ops.framework import EventBase, EventSource, StoredState
from ops.main import main
from ops.model import (
    ActiveStatus,
    MaintenanceStatus,
    WaitingStatus,
)

from interface_http import HTTPServer
from interface_mysql import MySQLServer, MySQLServerError
from oci_image import OCIImageResource, FetchError


class ConfigurePodEvent(EventBase):
    pass


class ServeWebsiteEvent(EventBase):
    pass


class GitLabK8sCharmEvents(CharmEvents):
    configure_pod = EventSource(ConfigurePodEvent)
    serve_website = EventSource(ServeWebsiteEvent)


class NotLeaderError(Exception):
    def __init__(self):
        super().__init__('not leader')
        self.status = WaitingStatus('Not leader')


class GitLabK8sCharm(CharmBase):
    state = StoredState()

    def __init__(self, framework, key):
        super().__init__(framework, key)

        self.website = HTTPServer(self, 'website')
        self.mysql = MySQLServer(self, 'mysql')
        self.gitlab_image = OCIImageResource(self, 'gitlab_image')

        self.state.is_started = getattr(self.state, 'is_started', False)
        self.state.has_website = getattr(self.state, 'has_website', False)

        self.framework.observe(self.on.start, self.check_ready)  # TODO: change to install
        self.framework.observe(self.on.leader_elected, self.check_ready)
        self.framework.observe(self.on.upgrade_charm, self.check_ready)
        self.framework.observe(self.on.config_changed, self.check_ready)
        self.framework.observe(self.mysql.on.database_available, self.check_ready)
        self.framework.observe(self.mysql.on.database_changed, self.check_ready)
        self.framework.observe(self.on.configure_pod, self.configure_pod)
        self.framework.observe(self.website.on.new_client, self.serve_website)

    def check_ready(self, event):
        try:
            self.mysql.database()
            self.gitlab_image.fetch()
            if not self.model.unit.is_leader():
                raise NotLeaderError()
        except (MySQLServerError, FetchError, NotLeaderError) as e:
            self.model.unit.status = e.status
        else:
            self.on.configure_pod.emit()

    def configure_pod(self, event):
        self.model.unit.status = MaintenanceStatus('Configuring pod')
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
        self.on.serve_website.emit()
        self.model.unit.status = ActiveStatus()

    def serve_website(self, event):
        if not self.state.is_started:
            return

        for client in self.website.clients:
            client.serve(hosts=[client.ingress_address],
                         port=self.model.config['http_port'])


if __name__ == '__main__':
    main(GitLabK8sCharm)
