# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
User and permission enums.
"""

from enum import Enum


class PermissionScope(str, Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    SHARE = "share"
    ADMIN = "admin"


class UserRole(str, Enum):
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"
    OPERATOR = "operator"
    TENANT = "tenant"
    SERVICE = "service"


__all__ = [
    "PermissionScope",
    "UserRole",
]
