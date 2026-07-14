from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends

from app.core.errors import AuthorizationError
from app.modules.auth.router import get_current_user


def require_roles(*allowed_roles: str) -> Callable:
    def dependency(user=Depends(get_current_user)):
        if user.role not in allowed_roles:
            raise AuthorizationError(user.role)
        return user

    return dependency
