"""pysamsung-dplug: async client for old Samsung air conditioners (DPLUG / port 2878)."""
from .client import (
    DEFAULT_PORT,
    AuthError,
    SamsungAcClient,
    SamsungAcError,
    async_probe,
    build_ssl_context,
    default_cert_path,
    parse_start_from,
)
from .commands import PowerUsageEntry
from .options import OptionCode
from .schedule import (
    EVERYDAY_TYPE,
    EVERYWEEK,
    ONCE,
    Schedule,
    mask_to_names,
    mask_to_weekdays,
    names_to_mask,
    weekdays_to_mask,
)
from .stream import SamsungAcStream

__all__ = [
    "SamsungAcClient",
    "SamsungAcStream",
    "SamsungAcError",
    "AuthError",
    "build_ssl_context",
    "async_probe",
    "default_cert_path",
    "parse_start_from",
    "OptionCode",
    "PowerUsageEntry",
    "Schedule",
    "ONCE",
    "EVERYDAY_TYPE",
    "EVERYWEEK",
    "mask_to_names",
    "names_to_mask",
    "mask_to_weekdays",
    "weekdays_to_mask",
    "DEFAULT_PORT",
]

__version__ = "0.9.1"
