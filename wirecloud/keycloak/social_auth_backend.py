# -*- coding: utf-8 -*-

# Copyright (c) 2019 Future Internet Consulting and Development Solutions S.L.

# This file is part of Wirecloud Keycloak plugin.

# Wirecloud is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# Wirecloud is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with Wirecloud.  If not, see <http://www.gnu.org/licenses/>.

import base64
import jwt
from urllib.parse import urljoin

from django.conf import settings
from social_core.backends.oauth import BaseOAuth2

from django.db.models.signals import post_save
from django.dispatch import receiver

from wirecloud.keycloak.utils import get_user_model, get_group_model


KEYCLOAK_AUTHORIZATION_ENDPOINT = 'auth/realms/{}/protocol/openid-connect/auth'
KEYCLOAK_ACCESS_TOKEN_ENDPOINT = 'auth/realms/{}/protocol/openid-connect/token'


class KeycloakOAuth2(BaseOAuth2):
    """Keycloak IDM OAuth authentication endpoint"""

    name = 'keycloak'
    ID_KEY = 'preferred_username'

    IDM_SERVER = getattr(settings, 'KEYCLOAK_SERVER', '')
    REALM = getattr(settings, 'KEYCLOAK_REALM', '')
    KEY = getattr(settings, 'KEYCLOAK_KEY', '')

    CLIENT_ID = getattr(settings, 'SOCIAL_AUTH_KEYCLOAK_KEY', '')

    ACCESS_TOKEN_URL = urljoin(IDM_SERVER, KEYCLOAK_ACCESS_TOKEN_ENDPOINT.format(REALM))
    AUTHORIZATION_URL = urljoin(IDM_SERVER, KEYCLOAK_AUTHORIZATION_ENDPOINT.format(REALM))

    REDIRECT_STATE = False
    ACCESS_TOKEN_METHOD = 'POST'
    SCOPE_VAR_NAME = 'FIWARE_EXTENDED_PERMISSIONS'
    EXTRA_DATA = [
        ('username', 'username'),
        ('refresh_token', 'refresh_token'),
        ('expires_in', 'expires'),
        ('roles', 'roles')
    ]

    def __init__(self, *args, **kwargs):
        super(KeycloakOAuth2, self).__init__(*args, **kwargs)

    def auth_headers(self):
        token = base64.urlsafe_b64encode(('{0}:{1}'.format(*self.get_key_and_secret()).encode())).decode()
        return {
            'Authorization': 'Basic {0}'.format(token)
        }

    def get_user_details(self, response):
        """Return user details from JWT token info"""

        global_role = getattr(settings, 'KEYCLOAK_GLOBAL_ROLE', False)
        roles = []

        if global_role:
            if 'realm_access' in response and 'roles' in response['realm_access']:
                roles = response['realm_access']['roles']
        else:
            if 'resource_access' in response and self.CLIENT_ID in response['resource_access'] and 'roles' in response['resource_access'][self.CLIENT_ID]:
                roles = response['resource_access'][self.CLIENT_ID]['roles']

        superuser = any(role.strip().lower() == "admin" for role in roles)
        group_roles = [role.strip().lower() for role in roles if role.strip().lower() != "admin"]

        return {
            'username': response.get('preferred_username'),
            'email': response.get('email') or '',
            'fullname': response.get('name') or '',
            'first_name': response.get('given_name') or '',
            'last_name': response.get('family_name') or '',
            'is_superuser': superuser,
            'is_staff': superuser,
            'roles': group_roles
        }

    def request_user_info(self, access_token):
        # Parse JWT to get user info
        public_key = "-----BEGIN PUBLIC KEY-----\n" + self.KEY + "\n-----END PUBLIC KEY-----"
        user_info = jwt.decode(access_token, public_key, algorithms='RS256', audience='account')
        return user_info

    def user_data(self, access_token, *args, **kwargs):
        return self.request_user_info(access_token)


@receiver(post_save, sender=get_user_model())
def add_user_groups(sender, instance, created, **kwargs):
    if instance.social_auth.count() > 0:
        social = instance.social_auth.all()[0]
        # Remove user groups to support removed roles
        instance.groups.clear()

        # Add user to role groups
        if 'roles' in social.extra_data:
            for role in social.extra_data['roles']:
                group_model = get_group_model()
                role_group, created = group_model.objects.get_or_create(name=role.strip().lower())
                instance.groups.add(role_group)
