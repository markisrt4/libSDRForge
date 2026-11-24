"""!
@brief Decode CRC-validated Mode S and ADS-B Extended Squitter frames.

Only DF17 messages with a valid 24-bit parity are accepted. This first
milestone decodes identification, barometric altitude and airborne velocity.
It does not demodulate IQ, decode CPR coordinates, or track aircraft.
"""

from __future__ import annotations

from dataclasses import dataclass

_POLY = 0xFFF409
_CHARSET = "#ABCDEFGHIJKLMNOPQRSTUVWXYZ#####_###############0123456789######"


@dataclass(frozen=True)
class AdsbMessage:
    """!
    @brief Parsed ADS-B frame fields and optional aircraft telemetry.
    """

    df: int
    icao: str
    type_code: int
    raw: bytes
    callsign: str | None = None
    altitude_ft: int | None = None
    speed_kt: float | None = None
    heading_deg: float | None = None
    vertical_rate_fpm: int | None = None
    cpr_odd: bool | None = None
    cpr_lat: int | None = None
    cpr_lon: int | None = None


def modes_crc(message: bytes) -> int:
    """!
    @brief Calculate the Mode S CRC remainder including transmitted parity.
    @param message Seven- or fourteen-byte Mode S frame.
    @return CRC remainder, zero for valid plain-CRC DF17 frames.


    A valid plain-CRC DF17 frame has remainder zero. Other Mode S downlink
    formats can use ICAO-address parity and are not supported here.
    """
    if len(message) not in (7, 14):
        raise ValueError("Mode S messages must contain 7 or 14 bytes")
    bits = int.from_bytes(message, "big")
    n = len(message) * 8
    for bit in range(n - 25, -1, -1):
        if bits & (1 << (bit + 24)):
            bits ^= (_POLY | (1 << 24)) << bit
    return bits & 0xFFFFFF


def append_crc(payload: bytes) -> bytes:
    """!
    @brief Append a plain CRC to an eleven-byte DF17 payload.
    @param payload Eleven-byte payload.
    @return Fourteen-byte frame with appended CRC.
    """
    if len(payload) != 11:
        raise ValueError("DF17 payload must be 11 bytes")
    frame = payload + b"\x00\x00\x00"
    return payload + modes_crc(frame).to_bytes(3, "big")


def _field(frame: int, total_bits: int, start: int, length: int) -> int:
    """Extract a field using the specification's 1-based, MSB-first positions."""
    return (frame >> (total_bits - start - length + 1)) & ((1 << length) - 1)


def decode_message(message: bytes | str) -> AdsbMessage | None:
    """!
    @brief Decode a CRC-valid DF17 frame without inferring missing telemetry.
    @param message Frame bytes or hexadecimal text.
    @return Decoded ADS-B message or None for unsupported frames.


    Strings may contain hex bytes, optionally wrapped in *...; as used by
    common text-based Mode S feeds.
    """
    if isinstance(message, str):
        value = message.strip().removeprefix("*").removesuffix(";")
        try:
            message = bytes.fromhex(value)
        except ValueError:
            return None
    if len(message) != 14 or (message[0] >> 3) != 17:
        return None
    if modes_crc(message):
        return None
    frame = int.from_bytes(message, "big")

    def field(start: int, length: int) -> int:
        return _field(frame, 112, start, length)

    icao = f"{field(9, 24):06X}"
    tc = field(33, 5)
    callsign: str | None = None
    altitude_ft: int | None = None
    speed_kt: float | None = None
    heading_deg: float | None = None
    vertical_rate_fpm: int | None = None
    cpr_odd: bool | None = None
    cpr_lat: int | None = None
    cpr_lon: int | None = None
    if 1 <= tc <= 4:
        chars = "".join(_CHARSET[field(41 + 6 * i, 6)] for i in range(8))
        callsign = chars.replace("_", " ").replace("#", "").strip()
    elif 9 <= tc <= 18:
        # Airborne position message: retain raw CPR for a future position
        # decoder; never present CPR fractions as geographic coordinates.
        altitude = field(41, 12)
        if altitude & 0x10:  # Q bit: 25-foot encoding
            n = ((altitude & 0xFE0) >> 1) | (altitude & 0xF)
            altitude_ft = 25 * n - 1000
        cpr_odd = bool(field(54, 1))
        cpr_lat = field(55, 17)
        cpr_lon = field(72, 17)
    elif tc == 19:
        subtype = field(38, 3)
        if subtype in (1, 2):
            ew = field(47, 10)
            ns = field(58, 10)
            if ew and ns:
                from math import atan2, degrees, hypot

                multiplier = 4 if subtype == 2 else 1
                vx = (-1 if field(46, 1) else 1) * (ew - 1) * multiplier
                vy = (-1 if field(57, 1) else 1) * (ns - 1) * multiplier
                speed_kt = hypot(vx, vy)
                heading_deg = (degrees(atan2(vx, vy)) + 360) % 360
            vr = field(70, 9)
            if vr:
                vertical_rate_fpm = (-1 if field(69, 1) else 1) * (vr - 1) * 64
    return AdsbMessage(
        df=17,
        icao=icao,
        type_code=tc,
        raw=message,
        callsign=callsign,
        altitude_ft=altitude_ft,
        speed_kt=speed_kt,
        heading_deg=heading_deg,
        vertical_rate_fpm=vertical_rate_fpm,
        cpr_odd=cpr_odd,
        cpr_lat=cpr_lat,
        cpr_lon=cpr_lon,
    )
