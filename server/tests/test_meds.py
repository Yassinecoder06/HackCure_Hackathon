"""Medication timeline: doctor prescribes, system schedules and reminds, nurse records (whitepaper 4.3)."""

from __future__ import annotations

from borj_server.alerts import FirstSeen, derive_alerts
from borj_server.calls import CallConfig
from borj_server.meds import MedsConfig, timeline
from borj_server.timeutil import parse_ts

from .conftest import login, make_client, openapi_validator

CFG = MedsConfig.load()  # ward time = UTC+1; overdue after 30 min


def prescribe(ingestor, make_event, **overrides):
    """Example: B04 / ADM-0004, 06:00 12:00 18:00 23:00 ward time from 2026-10-10."""
    return ingestor.handle(*make_event("prescription", **overrides))


def at(ts: str):
    return parse_ts(ts)


def test_doses_follow_ward_local_times(ingestor, make_event):
    ingestor.handle(*make_event("binding"))
    prescribe(ingestor, make_event)
    doses = timeline(ingestor.twin, at("2026-10-10T21:50:00Z"), CFG, hours=8)["doses"]
    assert [d["due"] for d in doses] == ["2026-10-10T22:00:00Z", "2026-10-11T05:00:00Z"]  # 23:00 and 06:00 local
    assert {d["status"] for d in doses} == {"due"}
    assert doses[0]["label"] == "Paracetamol 1 g oral"


def test_overdue_then_only_a_nurse_closes_the_dose(ingestor, make_event):
    ingestor.handle(*make_event("binding"))
    prescribe(ingestor, make_event)
    first = timeline(ingestor.twin, at("2026-10-10T22:31:00Z"), CFG, hours=1)["doses"][0]
    assert first["status"] == "overdue"

    # The patient's "I took my pills" is stored but never closes the dose.
    ingestor.handle(*make_event("med.patient-reported", bed="B04", admissionId="ADM-0004", doseId=first["doseId"],
                                ts="2026-10-10T22:35:00Z"))
    dose = timeline(ingestor.twin, at("2026-10-10T22:36:00Z"), CFG, hours=1)["doses"][0]
    assert (dose["status"], dose["patientReportedAt"]) == ("overdue", "2026-10-10T22:35:00Z")

    ingestor.handle(*make_event("med.nurse", doseId=first["doseId"], ts="2026-10-10T22:40:00Z"))
    dose = timeline(ingestor.twin, at("2026-10-10T22:41:00Z"), CFG, hours=1)["doses"][0]
    assert (dose["status"], dose["administeredBy"]) == ("given", "N1")


def test_overdue_dose_raises_an_alert(ingestor, make_event):
    ingestor.handle(*make_event("binding"))
    prescribe(ingestor, make_event)
    alerts = derive_alerts(ingestor.twin, {}, at("2026-10-10T22:31:00Z"), CallConfig.load(), FirstSeen(),
                           meds_cfg=CFG)
    overdue = [a for a in alerts if a["type"] == "dose_overdue"]
    assert len(overdue) == 1 and "Paracetamol" in overdue[0]["explanation"][0]


def test_discharged_patient_has_no_doses(ingestor, make_event):
    ingestor.handle(*make_event("binding"))
    prescribe(ingestor, make_event)
    ingestor.handle(*make_event("binding", action="discharge", ts="2026-10-10T22:20:00Z"))
    assert timeline(ingestor.twin, at("2026-10-10T22:30:00Z"), CFG, hours=8)["doses"] == []


def test_clashes_for_one_nurse(ingestor, make_event):
    for bed in ("B01", "B02", "B03", "B04"):
        ingestor.handle(*make_event("binding", bed=bed, admissionId=f"ADM-{bed}"))
        prescribe(ingestor, make_event, bed=bed, admissionId=f"ADM-{bed}", prescriptionId=f"RX-{bed}",
                  times=["23:00"])
    ingestor.handle(*make_event("assignment", changes=[{"bed": b, "toStaffId": "N1"}
                                                       for b in ("B01", "B02", "B03", "B04")]))
    clashes = timeline(ingestor.twin, at("2026-10-10T21:50:00Z"), CFG, hours=2)["clashes"]
    assert len(clashes) == 1 and "4 doses due within 15 min for N1" in clashes[0]["reason"]


def test_two_infusions_at_once_clash(ingestor, make_event):
    for bed in ("B01", "B02"):
        ingestor.handle(*make_event("binding", bed=bed, admissionId=f"ADM-{bed}"))
        prescribe(ingestor, make_event, bed=bed, admissionId=f"ADM-{bed}", prescriptionId=f"RX-{bed}",
                  drug="Ceftriaxone", dose="2 g", route="iv", isInfusion=True, times=["23:00"])
    clashes = timeline(ingestor.twin, at("2026-10-10T21:50:00Z"), CFG, hours=2)["clashes"]
    assert clashes and clashes[0]["reason"].startswith("2 infusions due within 15 min for unassigned beds")


def test_prescribe_and_record_over_the_api(tmp_path, make_event):
    with make_client(tmp_path, auto_suggest=False) as c:
        ingestor = c.app.state.ingestor
        ingestor.handle(*make_event("binding"))
        ingestor.clock.update_from_message({"simTs": "2026-10-10T21:50:00Z"})
        body = {"admissionId": "ADM-0004", "drug": "Paracetamol", "dose": "1 g", "route": "oral",
                "times": ["23:00"], "startDate": "2026-10-10"}

        login(c, "N1")
        assert c.post("/api/v1/wards/W1/prescriptions", json=body).status_code == 403  # only a doctor prescribes

        login(c, "DR1")
        created = c.post("/api/v1/wards/W1/prescriptions", json=body)
        assert created.status_code == 201, created.text
        assert not list(openapi_validator("Prescription").iter_errors(created.json()))
        dose_id = created.json()["doses"][0]["doseId"]
        not_nurse = c.post(f"/api/v1/wards/W1/doses/{dose_id}/administration",
                           json={"action": "given", "presence": "wristband_scan"})
        assert not_nurse.status_code == 403  # the doctor prescribes; a nurse records

        login(c, "N1")
        timeline_body = c.get("/api/v1/wards/W1/meds/timeline?hours=4").json()
        assert not list(openapi_validator("MedTimeline").iter_errors(timeline_body))
        bad = c.post(f"/api/v1/wards/W1/doses/{dose_id}/administration",
                     json={"action": "not_given", "presence": "none"})
        assert bad.status_code == 422  # a reason is required
        given = c.post(f"/api/v1/wards/W1/doses/{dose_id}/administration",
                       json={"action": "given", "presence": "wristband_scan"})
        assert (given.status_code, given.json()["status"], given.json()["administeredBy"]) == (200, "given", "N1")
        again = c.post(f"/api/v1/wards/W1/doses/{dose_id}/administration",
                       json={"action": "given", "presence": "wristband_scan"})
        assert again.status_code == 409
        audit = [(e["actor"], e["action"]) for e in ingestor.store.audit_entries(50)]
    assert ("DR1", "prescription.created") in audit and ("N1", "dose.given") in audit
