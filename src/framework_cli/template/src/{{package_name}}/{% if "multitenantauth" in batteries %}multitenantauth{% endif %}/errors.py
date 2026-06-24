"""Auth/authz error types + the generic forbidden message (never echo policy to a client)."""


class AuthError(Exception):
    """Base class for auth/authz domain errors."""


class LastAdminError(AuthError):
    """Raised when an operation would leave a tenant with zero admins."""


class DomainMismatchError(AuthError):
    """Raised when a role's domain doesn't match the assignment kind (tenant vs platform)."""


AUTHZ_FORBIDDEN_DETAIL = "You do not have permission to perform this action."
