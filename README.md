GitLab Charm for Kubernetes Models
==================================

To use, deploy the charm with an appropriate image resource:

```bash
docker pull gitlab/gitlab-ce:12.0.12-ce.0
juju deploy . --resource gitlab_image=gitlab/gitlab-ce:12.0.12-ce.0
```

Finally, deploy and relate a database:

```bash
juju deploy cs:~charmed-osm/mariadb-k8s
juju relate mariadb-k8s gitlab-k8s
```
