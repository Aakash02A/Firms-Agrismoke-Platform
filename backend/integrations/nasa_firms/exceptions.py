"""
NASA FIRMS Integration Exceptions
Domain-specific exceptions for error tracking and clear reporting.
"""

class FirmsError(Exception):
    """Base exception for all NASA FIRMS integration errors."""
    pass


class FirmsAuthenticationError(FirmsError):
    """Raised when MAP_KEY is missing, invalid, or unauthorized (401/403)."""
    pass


class FirmsRateLimitError(FirmsError):
    """Raised when NASA FIRMS API rate limit is exceeded (429)."""
    pass


class FirmsNetworkError(FirmsError):
    """Raised when connection fails, times out, or DNS fails."""
    pass


class FirmsParseError(FirmsError):
    """Raised when NASA CSV response format is malformed or unparseable."""
    pass


class FirmsValidationError(FirmsError):
    """Raised when query coordinates, day range, or date parameters are invalid."""
    pass
