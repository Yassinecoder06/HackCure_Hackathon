"""Bed and Device Binding registry for the gateway.

Tracks which medical devices and admissions are bound to each bed in the ward.
Updated dynamically when binding events arrive from staff wristband scans.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

log = logging.getLogger(__name__)


class BindingRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.device_to_bed: dict[str, str] = {}
        self.bed_to_devices: dict[str, set[str]] = {}
        self.bed_to_admission: dict[str, str] = {}

    def apply_binding_event(self, payload: dict[str, Any]) -> None:
        bed = payload.get("bed")
        action = payload.get("action")
        admission_id = payload.get("admissionId")
        device_id = payload.get("deviceId")

        if not bed:
            return

        with self._lock:
            if action == "admit":
                if admission_id:
                    self.bed_to_admission[bed] = admission_id
                    log.info("Admitted %s to bed %s", admission_id, bed)

            elif action in ("discharge", "transfer_out"):
                self.bed_to_admission.pop(bed, None)
                log.info("Discharged bed %s", bed)

            elif action == "attach_device" and device_id:
                self.device_to_bed[device_id] = bed
                self.bed_to_devices.setdefault(bed, set()).add(device_id)
                log.info("Attached device %s to bed %s", device_id, bed)

            elif action == "detach_device" and device_id:
                self.device_to_bed.pop(device_id, None)
                if bed in self.bed_to_devices:
                    self.bed_to_devices[bed].discard(device_id)
                log.info("Detached device %s from bed %s", device_id, bed)

    def get_bed_for_device(self, device_id: str) -> str | None:
        with self._lock:
            return self.device_to_bed.get(device_id)

    def is_bed_occupied(self, bed: str) -> bool:
        with self._lock:
            return bed in self.bed_to_admission
