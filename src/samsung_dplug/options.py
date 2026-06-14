"""Decode AC_ADD2_OPTIONCODE into device capability flags.

Ported verbatim from the official Samsung app (OptionCodeHelper): each capability
is a bit in the option code. This is the authoritative source of what a given unit
supports — the device may report attributes for features it does not actually have,
so gate on these flags rather than on attribute presence.
"""
from __future__ import annotations


class OptionCode:
    OPTION_EGYPT = 1
    OPTION_SPI = 2
    OPTION_FAHRENHEIT = 4
    OPTION_TURBO_HEATMODE = 8  # Turbo / SoftCool
    OPTION_ECORUN_HEATMODE = 16
    OPTION_LOW_SOUND = 32  # Quiet
    OPTION_COOL_ONLY = 64  # heating available == NOT this bit
    OPTION_COLOR_OF_WIND = 128
    OPTION_COLD_AREA = 256
    OPTION_ENERGY_SIMULATOR = 512
    OPTION_LR_LOUVER = 1024  # left/right (horizontal) swing
    OPTION_HUMID_SENSOR = 2048
    OPTION_ECORUN_COOLMODE = 4096
    OPTION_DLIGHT_COOL = 8192
    OPTION_POWER_CONSUMPTION_TYPE = 16384  # power usage logging
    OPTION_INV_TYPE = 32768  # inverter

    def __init__(self, code: int) -> None:
        self.code = int(code)

    def _has(self, mask: int) -> bool:
        return (self.code & mask) == mask

    @classmethod
    def from_state(cls, state: dict) -> "OptionCode | None":
        v = (state or {}).get("AC_ADD2_OPTIONCODE")
        if v is not None and str(v).lstrip("-").isdigit():
            return cls(int(v))
        return None

    # --- capabilities (names mirror the app) ---
    @property
    def egypt(self) -> bool:
        return self._has(self.OPTION_EGYPT)

    @property
    def spi(self) -> bool:
        return self._has(self.OPTION_SPI)

    @property
    def fahrenheit(self) -> bool:
        return self._has(self.OPTION_FAHRENHEIT)

    @property
    def turbo_softcool(self) -> bool:
        return self._has(self.OPTION_TURBO_HEATMODE)

    @property
    def ecorun_heat(self) -> bool:
        return self._has(self.OPTION_ECORUN_HEATMODE)

    @property
    def quiet(self) -> bool:
        return self._has(self.OPTION_LOW_SOUND)

    @property
    def heater(self) -> bool:
        return not self._has(self.OPTION_COOL_ONLY)

    @property
    def color_of_wind(self) -> bool:
        return self._has(self.OPTION_COLOR_OF_WIND)

    @property
    def cold_area(self) -> bool:
        return self._has(self.OPTION_COLD_AREA)

    @property
    def energy_simulator(self) -> bool:
        return self._has(self.OPTION_ENERGY_SIMULATOR)

    @property
    def lr_swing(self) -> bool:
        return self._has(self.OPTION_LR_LOUVER)

    @property
    def humid_sensor(self) -> bool:
        return self._has(self.OPTION_HUMID_SENSOR)

    @property
    def ecorun_cool(self) -> bool:
        return self._has(self.OPTION_ECORUN_COOLMODE)

    @property
    def dlight_cool(self) -> bool:
        return self._has(self.OPTION_DLIGHT_COOL)

    @property
    def usage(self) -> bool:
        return self._has(self.OPTION_POWER_CONSUMPTION_TYPE)

    @property
    def inverter(self) -> bool:
        return self._has(self.OPTION_INV_TYPE)

    def as_dict(self) -> dict:
        return {
            n: getattr(self, n)
            for n in (
                "egypt", "spi", "fahrenheit", "turbo_softcool", "ecorun_heat",
                "quiet", "heater", "color_of_wind", "cold_area", "energy_simulator",
                "lr_swing", "humid_sensor", "ecorun_cool", "dlight_cool", "usage",
                "inverter",
            )
        }

    def __repr__(self) -> str:
        on = [k for k, v in self.as_dict().items() if v]
        return f"OptionCode({self.code}: {', '.join(on)})"
