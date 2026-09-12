"""Pure-Python port of the Hisense AC UART protocol.

This module is the executable specification used by the test suite. It mirrors
the logic in ``esphome/components/hisense/air_conditioner.cpp`` so we can
exercise the algorithm without flashing firmware.

Frame layout (all integers big-endian)::

    F4 F5 | <payload bytes> | CS_hi CS_lo | F4 FB

Checksum is the 16-bit unsigned sum of every byte in ``frame[2:-4]`` — i.e.
everything between the leading ``F4 F5`` header and the trailing checksum,
masked with ``0xFFFF``. The result is serialised most-significant byte first.

The :class:`StreamingParser` provides a *resync-safe* byte-at-a-time parser
that the firmware SHOULD use. The current C++ implementation does not resync
on garbage and is the root cause of the Home Assistant climate entity never
initialising — see ``tests/test_streaming_parser.py``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

HEADER = b"\xF4\xF5"
FOOTER = b"\xF4\xFB"

# Message-type bytes used at payload position 11 (0-indexed in full frame)
MSG_COMMAND = 0x65
MSG_QUERY = 0x66
MSG_RESPONSE = 0x01

# Climate mode codes (high nibble of payload[16]); 12 means powered off
MODE_FAN_ONLY = 0
MODE_HEAT = 1
MODE_COOL = 2
MODE_DRY = 3
MODE_AUTO = 4  # 4..7 all decode to AUTO in the firmware
MODE_OFF = 12

# Swing byte values written by send_status at status[32]
SWING_OFF = 0x50
SWING_VERTICAL = 0x30
SWING_HORIZONTAL = 0x70
SWING_BOTH = 0xF0

# Fan-mode lookup matching decode_wind_codes[19] in air_conditioner.cpp
FAN_OFF = "off"
FAN_AUTO = "auto"
FAN_LOW = "low"
FAN_FOCUS = "focus"
FAN_MEDIUM = "medium"
FAN_MIDDLE = "middle"
FAN_HIGH = "high"

FAN_CODES: dict[int, Optional[str]] = {
    0: FAN_OFF,
    1: FAN_AUTO,
    2: FAN_AUTO,
    10: FAN_LOW,
    12: FAN_FOCUS,
    14: FAN_MEDIUM,
    16: FAN_MIDDLE,
    18: FAN_HIGH,
}


class FrameError(ValueError):
    """Raised when a buffer cannot be parsed as a complete Hisense frame."""


# ---------------------------------------------------------------------------
# Checksum
# ---------------------------------------------------------------------------

def checksum(frame: bytes) -> int:
    """Return the 16-bit Hisense checksum for ``frame``.

    ``frame`` MUST include the leading ``F4 F5`` header. The checksum sums every
    byte from index 2 to the end of the supplied slice. Callers should pass the
    payload only (header + body, no trailing CS/footer) — exactly the slice the
    C++ ``send_raw`` hands to ``checksum``.
    """
    if len(frame) < 2:
        raise FrameError("frame too short to checksum")
    return sum(frame[2:]) & 0xFFFF


def checksum_bytes(frame: bytes) -> bytes:
    """Return the checksum of ``frame`` as a 2-byte big-endian sequence."""
    cs = checksum(frame)
    return bytes([(cs >> 8) & 0xFF, cs & 0xFF])


# ---------------------------------------------------------------------------
# Frame build / parse
# ---------------------------------------------------------------------------

def build_frame(payload: bytes) -> bytes:
    """Wrap ``payload`` (header + body, no CS/footer) into a full UART frame."""
    if not payload.startswith(HEADER):
        raise FrameError("payload must start with F4 F5 header")
    return payload + checksum_bytes(payload) + FOOTER


ESCAPE_BYTE = 0xF4


def stuff_wire(data: bytes) -> bytes:
    """Duplicate every literal 0xF4 in ``data`` (Hisense TX byte-stuffing).

    The AC de-stuffs on receive, and upstream templates (pslawinski
    messages.h) pre-stuff on transmit - e.g. temp_16_C's 0x01F4 checksum is
    emitted as ``01 F4 F4 F4 FB``. Without stuffing, any frame whose body or
    checksum contains 0xF4 collides with the F4 FB footer marker.
    """
    out = bytearray()
    for b in data:
        out.append(b)
        if b == ESCAPE_BYTE:
            out.append(ESCAPE_BYTE)
    return bytes(out)


def build_wire_frame(payload: bytes) -> bytes:
    """Like :func:`build_frame`, but with TX byte-stuffing applied.

    Header F4 F5 and footer F4 FB are sent literal; body bytes and the two
    checksum bytes are stuffed via :func:`stuff_wire`.
    """
    if not payload.startswith(HEADER):
        raise FrameError("payload must start with F4 F5 header")
    cs = checksum_bytes(payload)
    return payload[:2] + stuff_wire(payload[2:] + cs) + FOOTER


@dataclass(frozen=True)
class Frame:
    """Parsed Hisense UART frame."""

    payload: bytes  # bytes between header and checksum (no F4 F5, no CS, no F4 FB)
    raw: bytes      # original bytes including header/cs/footer
    checksum: int

    @property
    def body(self) -> bytes:
        return self.payload


def parse_frame(buf: bytes) -> Frame:
    """Parse ``buf`` as a complete Hisense UART frame.

    Raises :class:`FrameError` for any malformed input: bad header, bad footer,
    too short, or checksum mismatch.
    """
    if len(buf) < 6:
        raise FrameError(f"frame too short: {len(buf)} bytes")
    if buf[:2] != HEADER:
        raise FrameError(f"bad header: {buf[:2].hex()}")
    if buf[-2:] != FOOTER:
        raise FrameError(f"bad footer: {buf[-2:].hex()}")

    body = buf[2:-4]
    cs_hi, cs_lo = buf[-4], buf[-3]
    embedded = (cs_hi << 8) | cs_lo

    calc = sum(body) & 0xFFFF
    if calc != embedded:
        raise FrameError(
            f"checksum mismatch: calc=0x{calc:04X} embedded=0x{embedded:04X}"
        )
    return Frame(payload=body, raw=buf, checksum=embedded)


def parse_frame_lenient(buf: bytes) -> Frame:
    """Parse ``buf`` with one recovery pass for the ``F4 F4 FB`` corruption.

    Some Hisense indoor units occasionally emit a doubled ``0xF4`` byte
    immediately before the footer, producing ``... cs_hi cs_lo F4 F4 FB`` on
    the wire (frame is 1 byte longer than nominal). This helper mirrors the
    same recovery the C++ extractor performs: if strict parsing fails on a
    buffer whose final 3 bytes are ``F4 F4 FB``, drop one F4 and retry.
    All other corruption modes still raise :class:`FrameError`.
    """
    try:
        return parse_frame(buf)
    except FrameError:
        pass
    # Doubled-F4 recovery: ... F4 F4 FB
    if len(buf) >= 9 and buf[-3:] == b"\xF4\xF4\xFB":
        candidate = buf[:-3] + b"\xF4\xFB"
        return parse_frame(candidate)
    # Re-raise the original (strict) error for visibility.
    return parse_frame(buf)


def find_frame_end(buf: bytes, start: int = 0) -> Optional[int]:
    """Return the index just past the next ``F4 FB`` footer, or ``None``."""
    idx = buf.find(FOOTER, start)
    if idx < 0:
        return None
    return idx + 2


# ---------------------------------------------------------------------------
# Streaming parser (the resync-safe replacement for the C++ logic)
# ---------------------------------------------------------------------------

class StreamingState(Enum):
    """State of the resync-safe byte-at-a-time parser."""

    SEEK_F4 = "seek_f4"      # Looking for the first header byte
    SEEK_F5 = "seek_f5"      # Saw 0xF4, expecting 0xF5
    IN_BODY = "in_body"      # Header confirmed, collecting body bytes
    SEEK_FB = "seek_fb"      # Saw a trailing 0xF4, expecting 0xFB


@dataclass
class StreamingParser:
    """Resync-safe byte-stream parser for Hisense UART frames.

    Feed bytes one at a time (or in chunks) via :meth:`feed`. Whenever a
    complete, valid frame is recognised it is returned and the internal buffer
    is reset to look for the next frame. Garbage bytes between frames are
    silently dropped without disrupting the next frame's recognition. This is
    the behaviour the firmware MUST adopt to make the Home Assistant climate
    entity initialise reliably (see test_streaming_parser).
    """

    buf: bytearray = field(default_factory=bytearray)
    state: StreamingState = StreamingState.SEEK_F4
    drops: int = 0  # number of pre-header garbage bytes silently dropped

    # Largest frame we expect in practice. 82-byte status response + a bit of
    # slack; we ABORT the current candidate if no footer arrives within this
    # window, and rescan the discarded bytes for a fresh F4 F5 header.
    MAX_FRAME_SIZE = 100

    def reset(self) -> None:
        self.buf.clear()
        self.state = StreamingState.SEEK_F4

    def feed(self, data: bytes) -> list[Frame]:
        """Feed raw bytes; return any complete frames recognised this call."""
        out: list[Frame] = []
        for b in data:
            frame = self._feed_byte(b)
            if frame is not None:
                out.append(frame)
            # Resync: if we've exceeded the size cap without finding a footer,
            # drop the current candidate and rescan its tail for a new F4 F5.
            if self.state is not StreamingState.SEEK_F4 and \
                    len(self.buf) > self.MAX_FRAME_SIZE:
                out.extend(self._abandon_and_rescan())
        # Surface any frames recovered from inside a discarded candidate.
        if hasattr(self, "_pending_recovered"):
            out.extend(self._pending_recovered)
            self._pending_recovered = []
        return out

    def _abandon_and_rescan(self) -> list[Frame]:
        """Discard the current candidate frame and re-feed its tail.

        Called when no footer has arrived within ``MAX_FRAME_SIZE`` bytes -
        the leading F4 F5 we latched onto was almost certainly a false match
        (or the frame was truncated and we accidentally absorbed the next
        frame's bytes). Re-scan everything after the first byte for a fresh
        header.
        """
        discarded = bytes(self.buf[1:])  # skip the spurious F4 we latched onto
        dropped_count = 1
        self.drops += dropped_count
        self.reset()
        return self.feed(discarded)

    def _feed_byte(self, b: int) -> Optional[Frame]:
        # State 1: hunting for 0xF4
        if self.state is StreamingState.SEEK_F4:
            if b == 0xF4:
                self.buf.append(b)
                self.state = StreamingState.SEEK_F5
            else:
                self.drops += 1
            return None

        # State 2: saw 0xF4, expecting 0xF5
        if self.state is StreamingState.SEEK_F5:
            if b == 0xF5:
                self.buf.append(b)
                self.state = StreamingState.IN_BODY
            elif b == 0xF4:
                # 0xF4 0xF4 - keep latest 0xF4 as candidate header start
                self.drops += 1  # the earlier F4 was garbage
                # buf already contains one F4
            else:
                # 0xF4 <other> - both bytes were garbage; resync
                self.drops += 2
                self.buf.clear()
                self.state = StreamingState.SEEK_F4
            return None

        # State 3: inside body, watching for footer 0xF4 0xFB
        if self.state is StreamingState.IN_BODY:
            self.buf.append(b)
            if b == 0xF4:
                self.state = StreamingState.SEEK_FB
            if len(self.buf) > self.MAX_FRAME_SIZE:
                # Runaway - abandon and try to resync
                self.reset()
            return None

        # State 4: saw 0xF4 inside body, expecting 0xFB to complete footer
        if self.state is StreamingState.SEEK_FB:
            self.buf.append(b)
            if b == 0xFB:
                raw = bytes(self.buf)
                self.reset()
                # Validate length, checksum, header
                if len(raw) < 8:
                    return None
                try:
                    return parse_frame(raw)
                except FrameError:
                    # The "frame" we just closed was bogus. Rescan its
                    # interior for a real F4 F5 header that we may have
                    # incorrectly absorbed - this is exactly the truncated-
                    # frame scenario from output.txt 08:57:13.
                    self._rescan(raw[1:])
                    return None
            elif b == 0xF4:
                return None
            else:
                self.state = StreamingState.IN_BODY
            return None

        return None  # unreachable

    def _rescan(self, data: bytes) -> None:
        """Replay ``data`` through the parser, salvaging any nested frame.

        Used when a closed candidate failed validation: the bytes between the
        spurious header and the trailing footer may themselves contain a real
        ``F4 F5 … F4 FB`` frame that was mistakenly absorbed.
        """
        # Feed without recursion-into-rescan: we want any frames found in the
        # tail to surface to the caller, so stash them on an instance buffer.
        self._pending_recovered: list[Frame] = getattr(
            self, "_pending_recovered", []
        )
        for b in data:
            frame = self._feed_byte(b)
            if frame is not None:
                self._pending_recovered.append(frame)

    # Pythonic convenience
    def __len__(self) -> int:
        return len(self.buf)


# ---------------------------------------------------------------------------
# Mode / temperature / swing / fan encoding
# ---------------------------------------------------------------------------

def encode_mode_byte(mode: int, power_on: bool) -> int:
    """Encode the climate mode + power into the byte stored at status[18].

    Reproduces the bit-pattern from ``send_status`` in air_conditioner.cpp::

        if (!power_on): byte = 0b00000100
        else:           byte = ((mode << 1) | 1) << 4 | 0b00001100
    """
    if not power_on:
        return 0b00000100
    return (((mode << 1) | 1) << 4) | 0b00001100


def decode_mode_byte(byte: int) -> tuple[int, bool]:
    """Inverse of :func:`encode_mode_byte`."""
    power_on = bool(byte & 0b00001000)
    if not power_on:
        return MODE_OFF, False
    encoded = (byte >> 4) & 0x0F
    mode = (encoded - 1) >> 1
    return mode, True


def resolve_target_temp_for_send(
    requested: float | None,
    current: float | None,
    *,
    default: float = 22.0,
) -> float | None:
    """Mirror the C++ ``send_status`` target-temperature handling.

    HA may call ``control()`` with only a mode change (no target). In that
    case the firmware re-uses ``this->target_temperature``. On the very
    first call after boot ``this->target_temperature`` is NaN, which used
    to slip through into a uint8_t cast and trigger the "Not valid tmp!"
    log flood when the user changed mode from OFF to e.g. FAN_ONLY.

    The new contract:
      * If ``requested`` is finite and in 16..30 it wins.
      * Else if ``current`` is finite and in 16..30 it is used.
      * Else ``default`` (22 C) is used.
      * If ``requested`` was given but is out of range / NaN we return
        ``None`` to signal "refuse to send".
    """

    def _ok(v):
        return v is not None and math.isfinite(v) and 16.0 <= v <= 30.0

    if requested is not None:
        if not _ok(requested):
            return None
        return float(requested)
    if _ok(current):
        return float(current)
    return float(default)


def encode_target_temp_byte(celsius: int) -> int:
    """Encode the target temperature (°C) into the byte at status[19]."""
    return ((celsius & 0xFF) << 1) | 1


def decode_target_temp_byte(byte: int) -> int:
    """Inverse of :func:`encode_target_temp_byte`."""
    return (byte >> 1) & 0xFF


TEMP_MIN_C = 16
TEMP_MAX_C = 30


def is_temp_in_range(celsius: int) -> bool:
    """Return ``True`` for set-points the firmware should accept (16..30 °C)."""
    return TEMP_MIN_C <= celsius <= TEMP_MAX_C


def decode_fan_speed(payload_byte: int) -> Optional[str]:
    """Decode payload[14] into a fan-mode string, or ``None`` for unknown."""
    return FAN_CODES.get(payload_byte)


def decode_swing(payload_byte: int) -> str:
    """Decode payload[33] swing bits into a label."""
    up_down = bool(payload_byte & 0b01000000)
    left_right = bool(payload_byte & 0b10000000)
    if up_down and left_right:
        return "both"
    if left_right:
        return "vertical"  # matches the C++ code's mapping
    if up_down:
        return "horizontal"
    return "off"


# ---------------------------------------------------------------------------
# Full decode of a status-response payload
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClimateState:
    """Decoded view of a Hisense status response - what HA should see."""

    power_on: bool
    mode: int                       # MODE_* constant (when power_on True)
    target_temp_c: int
    indoor_temp_c: int
    indoor_coil_temp_c: int
    outdoor_temp_c: int
    outdoor_coil_temp_c: int
    fan_mode: Optional[str]
    swing_mode: str


def decode_status_payload(payload: bytes) -> ClimateState:
    """Decode the body of a status response into a :class:`ClimateState`.

    ``payload`` is the slice between the ``F4 F5`` header and the checksum -
    exactly what ``AirConditioner::decode_message`` receives.

    NOTE on byte offsets: ``body[21]`` was previously believed to be indoor
    humidity, but on every observed Hisense status frame it is a static
    ``0x80`` flag byte. Outdoor temperature/coil values were also off by
    two bytes - they live in the ``body[42..45]`` block on real 76-byte
    payloads (``body[40]`` and ``body[41]`` are always ``0x00``).
    """
    if len(payload) < 44:
        raise FrameError(f"payload too short to decode: {len(payload)} bytes")

    mode_byte = payload[16]
    decoded_mode, power_on = decode_mode_byte(mode_byte)

    return ClimateState(
        power_on=power_on,
        mode=decoded_mode if power_on else MODE_OFF,
        target_temp_c=payload[17],
        indoor_temp_c=payload[18],
        indoor_coil_temp_c=payload[19],
        outdoor_temp_c=payload[42],
        outdoor_coil_temp_c=payload[43],
        fan_mode=decode_fan_speed(payload[14]),
        swing_mode=decode_swing(payload[33]),
    )
