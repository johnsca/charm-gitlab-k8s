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
from interface_mysql import MySQLServer
from oci_image import OCIImageResource


class GitLabK8sCharm(CharmBase):
    state = StoredState()

    def __init__(self, framework, key):
        super().__init__(framework, key)

        # This has to come first to ensure the charm state is initialized before any components observe the
        # start event, lest they emit something that we observe which expects the state to be initialized.
        self.framework.observe(self.on.start, self.init_state)

        self.website = HTTPServer(self, 'website')
        self.mysql = MySQLServer(self, 'mysql')
        self.gitlab_image = OCIImageResource(self, 'gitlab_image')

        # The order of these observe calls are significant. Any event which might lead to a "waiting" status
        # must be observed before any event that might lead to a "blocked" status, so that the user isn't left
        # with a status that obscures the fact that manual intervention is required with a less critical "waiting"
        # status. Similarly, any handler which depends on state data which is set by other handlers must be
        # registered as observers after those which control the state data they depend on.

        # Can only lead to either "waiting" status due to leadership, or "active".
        self.framework.observe(self.on.leader_elected, self.configure_pod)
        self.framework.observe(self.on.config_changed, self.configure_pod)

        # Could lead to either a "waiting" or "blocked" status from the relation, or the calling of configure_pod.
        self.framework.observe(self.mysql.on.database_available, self)
        self.framework.observe(self.mysql.on.database_changed, self.on_database_available)
        self.framework.observe(self.mysql.on.database_unavailable, self)

        # Can only lead to a "blocked" status or the calling of configure_pod.
        self.framework.observe(self.gitlab_image.on.image_available, self)
        self.framework.observe(self.gitlab_image.on.image_failed, self)

        # Requires the state set set by configure_pod.
        self.framework.observe(self.website.on.new_client, self)

    def init_state(self, event):
        self.state.is_started = False
        self.state.has_image = False
        self.state.registry_path = None
        self.state.registry_user = None
        self.state.registry_pass = None
        self.state.database = None

    def on_image_available(self, event):
        self.state.has_image = True
        self.state.registry_path = event.registry_path
        self.state.username = event.username
        self.state.password = event.password
        # Optimistically try to configure the pod.
        self.configure_pod(event)

    def on_image_failed(self, event):
        self.state.has_image = False
        self.model.unit.status = event.status

    def on_database_available(self, event):
        self.state.database = dict(event.database)  # FIXME: Remove need for dict wrapper
        # Optimistically try to configure the pod.
        self.configure_pod(event)

    def on_database_unavailable(self, event):
        self.state.database = None
        self.model.unit.status = event.status

    def configure_pod(self, event):
        if not (self.state.has_image and self.state.database):
            return
        # There is no "leadership lost" event to use to manage this status.
        if not self.model.unit.is_leader():
            self.model.unit.status = WaitingStatus('Only leader can configure pod')
            return
        self.model.unit.status = MaintenanceStatus('Configuring pod')
        db = self.mysql.database()
        self.model.pod.set_spec({
            'containers': [{
                'name': self.framework.model.app.name,
                'imageDetails': {
                    'imagePath': self.state.registry_path,
                    'username': self.state.username,
                    'password': self.state.password,
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

    def on_new_client(self, event):
        if not self.state.is_started:
            return event.defer()

        event.client.serve(hosts=[event.client.ingress_address],
                           port=self.model.config['http_port'])


if __name__ == '__main__':
    main(GitLabK8sCharm)
