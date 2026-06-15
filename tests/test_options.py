"""Tests for the AC_ADD2_OPTIONCODE capability decoder."""
from samsung_dplug import OptionCode


def test_individual_bits():
    assert OptionCode(OptionCode.OPTION_SPI).spi is True
    assert OptionCode(OptionCode.OPTION_LOW_SOUND).quiet is True
    assert OptionCode(OptionCode.OPTION_COLOR_OF_WIND).color_of_wind is True
    assert OptionCode(OptionCode.OPTION_LR_LOUVER).lr_swing is True
    assert OptionCode(0).spi is False


def test_heater_is_negated_cool_only():
    # COOL_ONLY set -> no heater; clear -> heater available.
    assert OptionCode(OptionCode.OPTION_COOL_ONLY).heater is False
    assert OptionCode(0).heater is True


def test_combined_mask():
    oc = OptionCode(OptionCode.OPTION_SPI | OptionCode.OPTION_LOW_SOUND)
    assert oc.spi and oc.quiet
    assert not oc.color_of_wind


def test_from_state():
    assert OptionCode.from_state({"AC_ADD2_OPTIONCODE": "34"}).code == 34  # SPI|LOW_SOUND
    assert OptionCode.from_state({"AC_ADD2_OPTIONCODE": "-1"}).code == -1
    assert OptionCode.from_state({}) is None
    assert OptionCode.from_state({"AC_ADD2_OPTIONCODE": "x"}) is None


def test_as_dict_keys_stable():
    d = OptionCode(0).as_dict()
    for key in ("spi", "quiet", "heater", "color_of_wind", "lr_swing", "usage", "inverter"):
        assert key in d
