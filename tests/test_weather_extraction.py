"""Hardware-independent weather extraction tests."""
from sdrforge.weather import extract_observation, parse_same_header


def test_explicit_weather_observation():
    result = extract_observation(
        "Temperature is 42. Winds northwest at 12 miles per hour. Relative humidity 65 percent.",
        frequency_hz=162_550_000,
    )
    assert result.temperature_f == 42
    assert result.wind_direction == "northwest"
    assert result.wind_mph == 12
    assert result.relative_humidity_percent == 65

def test_missing_fields_are_not_invented():
    result = extract_observation("A chance of showers tonight.", frequency_hz=162_400_000)
    assert result.temperature_f is None
    assert result.wind_mph is None

def test_same_header():
    result = parse_same_header("ZCZC-WXR-TOR-026099-026125+0030-3211430-KXYZ/NWS-")
    assert result is not None
    assert result.event == "TOR"
    assert result.location_codes == ("026099", "026125")
    assert result.duration == "0030"

def test_invalid_same_header():
    assert parse_same_header("This is a weather forecast") is None
