"""Device Adapter interfaces and frame validation for the gateway.

All adapters are strictly read-only (whitepaper 4.1).
Includes CRC32 frame checksum verification for device streams.
"""

from __future__ import annotations

import abc
import binascii
import json
import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class DeviceReading:
    device_id: str
    params: dict[str, Any]
    seq: int
    raw_frame: str


class DeviceAdapter(abc.ABC):
    """Abstract base class for all gateway device adapters. Strictly read-only."""

    @abc.abstractmethod
    def read_frame(self) -> DeviceReading | None:
        """Fetch the next reading from the device stream."""
        raise NotImplementedError

    def close(self) -> None:  # noqa: B027
        pass


class FrameCrcError(ValueError):
    """Raised when a raw device frame fails its checksum or CRC."""


def format_device_frame(seq: int, device_id: str, params: dict[str, Any]) -> str:
    """Format a line-based device frame with trailing CRC32 checksum."""
    body = f"FRAME|{seq}|{device_id}|{json.dumps(params, separators=(',', ':'))}"
    crc = binascii.crc32(body.encode("utf-8")) & 0xFFFFFFFF
    return f"{body}|{crc:08X}\n"


def parse_device_frame(line: str) -> DeviceReading:
    """Parse and verify CRC32 of a raw device frame line."""
    line = line.strip()
    parts = line.split("|", 4)
    if len(parts) != 5 or parts[0] != "FRAME":
        raise FrameCrcError(f"Malformed device frame: {line}")

    seq_str, dev_id, params_str, crc_hex = parts[1], parts[2], parts[3], parts[4]

    # Verify CRC32
    body = f"FRAME|{seq_str}|{dev_id}|{params_str}"
    expected_crc = binascii.crc32(body.encode("utf-8")) & 0xFFFFFFFF
    try:
        actual_crc = int(crc_hex, 16)
    except ValueError as exc:
        raise FrameCrcError(f"Invalid CRC hex in frame: {crc_hex}") from exc

    if expected_crc != actual_crc:
        raise FrameCrcError(
            f"Frame CRC mismatch for {dev_id}: expected {expected_crc:08X}, got {actual_crc:08X}"
        )

    try:
        params = json.loads(params_str)
    except json.JSONDecodeError as exc:
        raise FrameCrcError(f"Invalid JSON payload in frame: {exc}") from exc

    return DeviceReading(
        device_id=dev_id,
        params=params,
        seq=int(seq_str),
        raw_frame=line,
    )


class ReplayAdapter(DeviceAdapter):
    """Replays device frames from an iterable or file while verifying CRC32 on every frame."""

    def __init__(self, frames: list[str]) -> None:
        self.frames = list(frames)
        self.index = 0

    def read_frame(self) -> DeviceReading | None:
        if self.index >= len(self.frames):
            return None
        line = self.frames[self.index]
        self.index += 1
        return parse_device_frame(line)
