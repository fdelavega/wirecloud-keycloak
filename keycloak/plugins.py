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

import os

from django.conf import settings
from django.conf.urls import url
from django.utils.translation import ugettext_lazy as _
from django.views.decorators.cache import cache_page

from wirecloud.platform.core.plugins import get_version_hash
from wirecloud.platform.localcatalogue.utils import install_component
from wirecloud.platform.markets.utils import MarketManager
from wirecloud.platform.models import CatalogueResource
from wirecloud.platform.plugins import WirecloudPlugin
from wirecloud.platform.workspace.utils import create_workspace, delete_workspace


try:
    from social_django.utils import BACKENDS, get_backend, load_strategy
    KEYCLOAK_SOCIAL_AUTH_BACKEND = get_backend(BACKENDS, 'keycloak')(load_strategy())

    IDM_SUPPORT_ENABLED = 'wirecloud.keycloak' in settings.INSTALLED_APPS and 'social_django' in settings.INSTALLED_APPS \
        and getattr(settings, 'IDM_BACKEND', '') == 'keycloak'
except:
    IDM_SUPPORT_ENABLED = False


def auth_keycloak_token(auth_type, token):

    from social_django.models import UserSocialAuth
    user_data = KEYCLOAK_SOCIAL_AUTH_BACKEND.user_data(token)
    return UserSocialAuth.objects.get(provider='keycloak', uid=user_data['username']).user


class KeycloakPlugin(WirecloudPlugin):
    def get_urls(self):

        if IDM_SUPPORT_ENABLED:
            from wirecloud.keycloak.views import oauth_discovery
            return (
                url('^.well-known/oauth$', cache_page(7 * 24 * 60 * 60, key_prefix='well-known-oauth-%s' % get_version_hash())(oauth_discovery), name='oauth.discovery'),
            )
        else:
            return ()

    def get_api_auth_backends(self):

        if IDM_SUPPORT_ENABLED:
            return {
                'Bearer': auth_keycloak_token,
            }
        else:
            return {}

    def get_constants(self):
        constants = {}

        if IDM_SUPPORT_ENABLED:
            global KEYCLOAK_SOCIAL_AUTH_BACKEND
            import wirecloud.keycloak.social_auth_backend
            constants["FIWARE_IDM_SERVER"] = KEYCLOAK_SOCIAL_AUTH_BACKEND.IDM_SERVER

        return constants

    def get_proxy_processors(self):
        return ('wirecloud.keycloak.proxy.IDMTokenProcessor',)

    def get_platform_context_definitions(self):
        # Using default FIWARE token parameter for compatibility with existing widgets
        return {
            'fiware_token_available': {
                'label': _('FIWARE token available'),
                'description': _('Indicates if the current user has associated a FIWARE auth token that can be used for accessing other FIWARE resources'),
            },
        }

    def get_platform_context_current_values(self, user):
        # Work around bug when running manage.py compress
        fiware_token_available = IDM_SUPPORT_ENABLED and user.is_authenticated() and user.social_auth.filter(provider='keycloak').exists()
        return {
            'fiware_token_available': fiware_token_available
        }

    def get_django_template_context_processors(self):
        context = {}

        # Using FIWARE name in context for compatibility with existing templates
        if IDM_SUPPORT_ENABLED:
            context["FIWARE_IDM_SERVER"] = getattr(settings, "KEYCLOAK_IDM_SERVER", wirecloud.keycloak.social_auth_backend.IDM_SERVER)
            context["FIWARE_IDM_PUBLIC_URL"] = getattr(settings, "KEYCLOAK_IDM_SERVER", wirecloud.keycloak.social_auth_backend.IDM_SERVER)
        else:
            context["FIWARE_IDM_SERVER"] = None
            context["FIWARE_IDM_PUBLIC_URL"] = None

        return context
