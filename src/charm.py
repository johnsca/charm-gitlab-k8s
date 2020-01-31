#!/usr/bin/env python3

import sys
sys.path.append('lib')

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import (
    ActiveStatus,
    MaintenanceStatus,
    ModelError,
    WaitingStatus,
)

from interface_http import HTTPServer
from interface_mysql import MySQLClient
from oci_image import OCIImageResource


class GitLabK8sCharm(CharmBase):
    state = StoredState()

    def __init__(self, framework, key):
        super().__init__(framework, key)

        self.state.set_default(is_started=False)

        self.website = HTTPServer(self, 'website')
        self.mysql = MySQLClient(self, 'mysql')
        self.gitlab_image = OCIImageResource(self, 'gitlab_image')

        self.framework.observe(self.on.leader_elected, self.configure_pod)
        self.framework.observe(self.on.config_changed, self.configure_pod)
        self.framework.observe(self.on.upgrade_charm, self.configure_pod)
        self.framework.observe(self.mysql.on.database_available, self.configure_pod)
        self.framework.observe(self.mysql.on.database_changed, self.configure_pod)
        self.framework.observe(self.mysql.on.database_lost, self)

        # Must come last to ensure it happens after configure_pod.
        self.framework.observe(self.website.on.new_client, self)

    def verify_leadership(self):
        # This only seems to happen as something of a race condition, where we might reach this code
        # before Juju has informed us that we're the leader. Conceptually, I'm not even sure why charm
        # code would run on a non-leader unit for a K8s charm, since it can't make any meaningful changes.
        if not self.model.unit.is_leader():
            raise LeadershipError()

    def configure_pod(self, event):
        try:
            # The order of these checks is important for the priority of the status from any issues.
            # Image resource issues are always blocking, DB relation issues may be blocking or waiting,
            # and lack of leadership is always waiting.
            image_details = self.gitlab_image.fetch()
            db = self.mysql.database()
            self.verify_leadership()
        except ModelError as e:
            self.model.unit.status = e.status
            return
        self.model.unit.status = MaintenanceStatus('Configuring pod')
        self.model.pod.set_spec({
            'containers': [{
                'name': self.framework.model.app.name,
                'imageDetails': image_details,
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

    def on_database_lost(self, event):
        self.model.unit.status = event.status

    def on_new_client(self, event):
        if not self.state.is_started:
            return event.defer()

        event.client.serve(hosts=[event.client.ingress_address],
                           port=self.model.config['http_port'])


class LeadershipError(ModelError):
    def __init__(self):
        super().__init__('not leader', WaitingStatus('Deferring to leader unit to configure pod'))


if __name__ == '__main__':
    main(GitLabK8sCharm)
