"""
Check `Plugin Writer's Guide`_ for more details.

.. _Plugin Writer's Guide:
    https://docs.pulpproject.org/pulpcore/plugins/plugin-writer/index.html
"""

from django.db import models
from pulpcore.plugin.models import BaseModel, EncryptedTextField, AutoAddObjPermsMixin
from pulpcore.app.util import get_domain_pk


class UpstreamPulp(BaseModel, AutoAddObjPermsMixin):
    name = models.TextField(db_index=True)
    pulp_domain = models.ForeignKey("Domain", default=get_domain_pk, on_delete=models.PROTECT)

    base_url = models.TextField()
    api_root = models.TextField(default="pulp")
    domain = models.TextField(null=True)

    ca_cert = models.TextField(null=True)
    client_cert = models.TextField(null=True)
    client_key = EncryptedTextField(null=True)
    tls_validation = models.BooleanField(default=True)

    username = EncryptedTextField(null=True)
    password = EncryptedTextField(null=True)

    # TODO: Remove this field in next breaking change release
    pulp_label_select = models.TextField(null=True)
    q_select = models.TextField(null=True)

    last_replication = models.DateTimeField(null=True)

    content_origin = models.TextField(null=True)

    class Meta:
        unique_together = ("name", "pulp_domain")
        permissions = [
            ("replicate_upstreampulp", "Can start a replication task"),
            ("manage_roles_upstreampulp", "Can manage roles on upstream pulps"),
        ]

    def set_last_replication_timestamp(self, timestamp):
        self.last_replication = timestamp
        # enforce the update without changing pulp_last_updated
        self.save(update_fields=["last_replication"])
