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
from .options import OptionCode
from .stream import SamsungAcStream

__all__ = [
    "SamsungAcClient",
    "SamsungAcStream",
    "SamsungAcError",
    "AuthError",
    "build_ssl_context",
    "async_probe",
    "default_cert_path",
    "OptionCode",
    "DEFAULT_PORT",
]

__version__ = "0.4.0"
