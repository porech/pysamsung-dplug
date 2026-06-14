"""pysamsung-dplug: async client for old Samsung air conditioners (DPLUG / port 2878)."""
from .client import (
    DEFAULT_PORT,
    AuthError,
    SamsungAcClient,
    SamsungAcError,
    async_probe,
    build_ssl_context,
    default_cert_path,
)

__all__ = [
    "SamsungAcClient",
    "SamsungAcError",
    "AuthError",
    "build_ssl_context",
    "async_probe",
    "default_cert_path",
    "DEFAULT_PORT",
]

__version__ = "0.1.0"
