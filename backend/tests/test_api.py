"""The HTTP API with an in-memory database and a stand-in page reader."""

from __future__ import annotations

import asyncio
import io
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient
from PIL import Image

import extract
import main
from helpers import PAGE_1, PAGE_2, WORKBOOK, build_workbook, load_report, requires_workbook, sign_in

TODAY = date(2026, 11, 12)


@pytest.fixture
def client(monkeypatch):
    """Signed in as an admin, who may do everything these tests do. Who may do
    what is tested in test_auth.py."""
    monkeypatch.setattr(main, "db", AsyncMongoMockClient()["ttps_test"])
    monkeypatch.setattr(main, "_today", lambda: TODAY)
    with TestClient(main.app) as c:  # runs the lifespan (index creation) too
        sign_in(c, "admin")
        yield c


class FakeReader:
    """Stands in for extract.extract_report: returns (or raises) queued results."""

    def __init__(self, *results):
        self.queue = list(results)
        self.calls: list[dict] = []

    async def __call__(self, image, recheck=None):
        self.calls.append({"size": image.size, "recheck": recheck})
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return extract.Extraction(report=item, model="fake-reader", usage={"inputTokens": 1, "outputTokens": 2})


@pytest.fixture
def reader(monkeypatch):
    def install(*results) -> FakeReader:
        fake = FakeReader(*results)
        monkeypatch.setattr(main.extract, "extract_report", fake)
        return fake
    return install


def page_photo(size=(1119, 1599)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, format="JPEG")
    return buf.getvalue()


def upload(client, data: bytes | None = None, name: str = "page.jpg", mime: str = "image/jpeg"):
    return client.post("/api/reports", files={"file": (name, page_photo() if data is None else data, mime)})


def misread_page():
    report = load_report(PAGE_1)
    report.r04_gen.unit1 = "3.43"  # station total and PLF no longer agree
    return report


def entries(client, **params) -> list[dict]:
    response = client.get("/api/entries", params=params)
    assert response.status_code == 200, response.text
    return response.json()


# --- uploading a report ----------------------------------------------------------------------

def test_good_page_is_saved(client, reader):
    fake = reader(load_report(PAGE_1))
    response = upload(client, name="report.jpg")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "saved"
    assert (body["reportDate"], body["dataDate"]) == ("2026-11-04", "2026-11-03")
    assert body["attempts"] == 1 and body["replaced"] is False and body["changes"] == []
    assert body["missingDays"] == ["2026-11-01", "2026-11-02"]
    assert body["model"] == "fake-reader" and body["fileName"] == "report.jpg"
    assert all(c["ok"] for c in body["checks"] if c["severity"] == "error")
    assert fake.calls == [{"size": (1119, 1599), "recheck": None}]

    [entry] = entries(client, month="2026-11")
    assert entry["date"] == "2026-11-03"
    assert (entry["source"], entry["reportId"]) == ("report", body["id"])
    assert (entry["u1Gen"], entry["u2Gen"], entry["apc"], entry["u2Oil"]) == (3.48, 3.68, 0.7931, 9.0)
    assert entry["coalStock"] == 12246.51 and entry["u1Remark"] == "On Load"

    listed = client.get("/api/reports").json()
    assert [r["id"] for r in listed] == [body["id"]]
    assert "raw" not in listed[0] and "usage" not in listed[0]
    full = client.get(f"/api/reports/{body['id']}").json()
    assert full["raw"]["r04_gen"] == {"unit1": "3.48", "unit2": "3.68", "station": "7.16"}

    image = client.get(f"/api/reports/{body['id']}/image")
    assert image.status_code == 200 and image.headers["content-type"] == "image/jpeg"
    stored = Image.open(io.BytesIO(image.content))
    assert max(stored.size) <= extract.STORED_EDGE


def test_reupload_reports_replaced_and_changes(client, reader):
    reader(load_report(PAGE_1), load_report(PAGE_1))
    first = upload(client).json()
    # Someone corrected the day by hand in between.
    client.put("/api/entries/2026-11-03", json={"u1Gen": 3.4})
    second = upload(client).json()
    assert second["status"] == "saved" and second["replaced"] is True
    assert second["changes"] == [{"field": "u1Gen", "before": 3.4, "after": 3.48}]
    [entry] = entries(client, month="2026-11")
    assert entry["u1Gen"] == 3.48 and entry["reportId"] == second["id"] != first["id"]
    assert {r["id"] for r in client.get("/api/reports").json()} == {first["id"], second["id"]}


def test_misread_fixed_on_retry_is_saved(client, reader):
    fake = reader(misread_page(), load_report(PAGE_1))
    body = upload(client).json()
    assert body["status"] == "saved" and body["attempts"] == 2
    assert body["raw"]["r04_gen"]["unit1"] == "3.48"
    # The second look is told which cells did not add up.
    hints = fake.calls[1]["recheck"]
    assert hints and any("r04_gen.unit1" in h for h in hints)
    assert entries(client, month="2026-11")[0]["u1Gen"] == 3.48


def test_misread_twice_needs_review_then_confirm(client, reader):
    reader(misread_page(), misread_page())
    body = upload(client).json()
    assert body["status"] == "needs_review" and body["attempts"] == 2
    assert body["dataDate"] == "2026-11-03"
    failed = {c["id"] for c in body["checks"] if not c["ok"] and c["severity"] == "error"}
    assert {"gen_total", "plf_unit1"} <= failed
    assert entries(client, month="2026-11") == []

    response = client.post(f"/api/reports/{body['id']}/confirm", json={"entry": {"u1Gen": "3.48"}})
    assert response.status_code == 200, response.text
    confirmed = response.json()
    assert confirmed["status"] == "saved" and confirmed["confirmedAt"]
    [entry] = entries(client, month="2026-11")
    assert entry["u1Gen"] == 3.48 and entry["u2Gen"] == 3.68 and entry["reportId"] == body["id"]
    assert client.get(f"/api/reports/{body['id']}").json()["status"] == "saved"


def test_unreadable_date_needs_a_date_to_confirm(client, reader):
    report = load_report(PAGE_1)
    report.report_date = "smudged"
    reader(report, report)
    body = upload(client).json()
    assert body["status"] == "needs_review" and body["dataDate"] is None and body["missingDays"] == []
    url = f"/api/reports/{body['id']}/confirm"
    assert client.post(url, json={}).status_code == 400
    assert client.post(url, json={"dataDate": "3/11/2026"}).status_code == 400
    assert client.post(url, json={"dataDate": "2026-11-03"}).status_code == 200
    assert entries(client, month="2026-11")[0]["u1Gen"] == 3.48


def test_confirm_rejects_bad_corrections(client, reader):
    reader(misread_page(), misread_page())
    body = upload(client).json()
    response = client.post(f"/api/reports/{body['id']}/confirm", json={"entry": {"u1Gen": "three"}})
    assert response.status_code == 400
    assert entries(client, month="2026-11") == []
    assert client.post("/api/reports/nope/confirm", json={}).status_code == 404


def test_not_a_report_is_rejected(client, reader):
    report = load_report(PAGE_1)
    report.is_daily_system_report = False
    fake = reader(report)
    response = upload(client)
    assert response.status_code == 422
    assert len(fake.calls) == 1  # no second look at something that is not a report
    assert client.get("/api/reports").json() == []
    assert entries(client) == []


def test_not_an_image_is_rejected(client, reader):
    fake = reader()
    response = upload(client, data=b"%PDF-1.4 not an image", name="report.pdf", mime="application/pdf")
    assert response.status_code == 415
    assert fake.calls == []
    assert client.get("/api/reports").json() == []


def test_oversized_upload_is_rejected(client, reader):
    fake = reader()
    response = upload(client, data=b"\xff" * (extract.MAX_UPLOAD_BYTES + 1))
    assert response.status_code == 413
    assert fake.calls == []


def test_reader_error_surfaces_with_its_status(client, reader):
    reader(extract.ExtractionError("The reading service is not configured.", status=503))
    response = upload(client)
    assert response.status_code == 503
    assert response.json() == {"detail": "The reading service is not configured."}
    assert client.get("/api/reports").json() == []


def test_reader_error_on_retry_keeps_first_reading_for_review(client, reader):
    reader(misread_page(), extract.ExtractionError("Rate limited.", status=429))
    response = upload(client)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_review" and body["attempts"] == 2
    assert entries(client) == []
    assert [r["id"] for r in client.get("/api/reports").json()] == [body["id"]]


def test_cross_check_warnings_do_not_block_saving(client, reader):
    # 1 and 2 Nov are in, but 2 Nov's generation disagrees with the page's month-to-date total.
    for iso, u1 in (("2026-11-01", 3.48), ("2026-11-02", 3.66)):
        client.put(f"/api/entries/{iso}", json={"u1Gen": u1, "u2Gen": 3.5})
    reader(load_report(PAGE_1))
    body = upload(client).json()
    assert body["status"] == "saved" and body["missingDays"] == []
    warned = [c for c in body["checks"] if not c["ok"]]
    assert {c["id"] for c in warned} >= {"prog_gen_u1"}
    assert all(c["severity"] == "warn" for c in warned)


def test_second_page_lists_missing_days(client, reader):
    reader(load_report(PAGE_2))
    body = upload(client).json()
    assert body["status"] == "saved" and body["dataDate"] == "2026-11-10"
    assert body["missingDays"] == [f"2026-11-{d:02d}" for d in range(1, 10)]


# --- reports listing -------------------------------------------------------------------------

def test_reports_by_month_and_missing_ones(client, reader):
    reader(load_report(PAGE_1))
    report_id = upload(client).json()["id"]
    assert [r["id"] for r in client.get("/api/reports", params={"month": "2026-11"}).json()] == [report_id]
    assert client.get("/api/reports", params={"month": "2026-10"}).json() == []
    assert client.get("/api/reports", params={"month": "Nov-2026"}).status_code == 400
    assert client.get("/api/reports/nope").status_code == 404
    assert client.get("/api/reports/nope/image").status_code == 404


# --- daily entries ---------------------------------------------------------------------------

def test_entries_by_month_and_fiscal_year(client):
    for iso in ("2026-03-31", "2026-04-01", "2026-11-03", "2027-03-31", "2027-04-01"):
        assert client.put(f"/api/entries/{iso}", json={"u1Gen": 1}).status_code == 200
    assert [e["date"] for e in entries(client, month="2026-11")] == ["2026-11-03"]
    assert [e["date"] for e in entries(client, fy=2026)] == ["2026-04-01", "2026-11-03", "2027-03-31"]
    assert len(entries(client)) == 5
    assert client.get("/api/entries", params={"month": "2026-1"}).status_code == 400


def test_put_entry(client):
    response = client.put("/api/entries/2026-11-03", json={
        "u1Gen": "3.48", "u2Gen": 3.68, "u1Coal": "", "u1TripReason": "  BTL  ", "u2TripReason": "",
        "bogus": 1, "date": "2030-01-01", "source": "hacked",
    })
    assert response.status_code == 200, response.text
    entry = response.json()
    assert entry["date"] == "2026-11-03" and entry["source"] == "manual" and "bogus" not in entry
    assert (entry["u1Gen"], entry["u2Gen"], entry["u1Coal"]) == (3.48, 3.68, None)
    assert (entry["u1TripReason"], entry["u2TripReason"]) == ("BTL", None)
    # A later PUT changes only what it sends.
    entry = client.put("/api/entries/2026-11-03", json={"u2Gen": 3.7}).json()
    assert (entry["u1Gen"], entry["u2Gen"]) == (3.48, 3.7)


@pytest.mark.parametrize("value", ["abc", "nan", "inf", "-Infinity", True, [1], {"v": 1}])
def test_put_entry_rejects_non_numbers(client, value):
    response = client.put("/api/entries/2026-11-03", json={"u1Gen": value})
    assert response.status_code == 400
    assert entries(client) == []


@pytest.mark.parametrize("bad", ["2026-13-01", "2026-02-30", "20261103", "3-11-2026", "2026-11-3"])
def test_put_entry_rejects_bad_dates(client, bad):
    assert client.put(f"/api/entries/{bad}", json={"u1Gen": 1}).status_code == 400


# --- workbook import ---------------------------------------------------------------------------

def _workbook() -> bytes:
    day = {"u2Gen": 3.5, "u1Coal": 2500, "u2Coal": 2900, "apc": 0.8, "gcv": 3450, "u1Trip": 1, "u1Fo": 0.75}
    return build_workbook(
        {
            "2026-11-01": {"u1Gen": 3.48, **day},
            "2026-11-02": {"u1Gen": 3.56, **day},
            # Differs from the page uploaded for 3 Nov (which printed 3.48).
            "2026-11-03": {"u1Gen": 9.99, **day},
        },
        targets={"2026-11": {"u1": 100.0, "u2": 110.0}},
        coal_opening=500000.0,
    )


def _import(client, data: bytes, **params):
    return client.post("/api/import/workbook", params=params,
                       files={"file": ("book.xlsx", data, "application/octet-stream")})


def test_import_keeps_days_filled_from_a_report(client, reader):
    reader(load_report(PAGE_1))
    upload(client)
    response = _import(client, _workbook())
    assert response.status_code == 200, response.text
    assert response.json() == {"fy": 2026, "days": 3, "from": "2026-11-01", "to": "2026-11-03",
                               "added": 2, "updated": 1}
    day = {e["date"]: e for e in entries(client, month="2026-11")}
    # The report's figures stay; the workbook only fills what the page does not carry.
    assert day["2026-11-03"]["u1Gen"] == 3.48 and day["2026-11-03"]["u1Fo"] == 0.0
    assert day["2026-11-03"]["gcv"] == 3450.0 and day["2026-11-03"]["u1Trip"] == 1.0
    assert day["2026-11-03"]["source"] == "report"
    assert day["2026-11-01"]["source"] == "workbook" and day["2026-11-01"]["u1Fo"] == 0.75
    # Importing the same file again changes nothing.
    assert _import(client, _workbook()).json()["added"] == 0
    assert _import(client, _workbook()).json()["updated"] == 0


def test_import_overwrite_replaces_report_values(client, reader):
    reader(load_report(PAGE_1))
    upload(client)
    body = _import(client, _workbook(), overwrite="true").json()
    assert (body["added"], body["updated"]) == (2, 1)
    assert {e["date"]: e for e in entries(client, month="2026-11")}["2026-11-03"]["u1Gen"] == 9.99


def test_import_stores_targets_and_stocks(client):
    _import(client, _workbook())
    config = client.get("/api/config/2026").json()
    assert config["monthlyTargets"] == {"2026-11": {"u1": 100.0, "u2": 110.0}}
    assert config["coalStockAnchors"] == [{"date": "2026-04-01", "stock": 500000.0}]


def test_import_rejects_other_files(client):
    response = _import(client, b"not a workbook")
    assert response.status_code == 422
    assert "xlsx" in response.json()["detail"]


@requires_workbook
def test_import_real_workbook(client):
    data = WORKBOOK.read_bytes()
    body = _import(client, data).json()
    assert body == {"fy": 2026, "days": 218, "from": "2026-04-01", "to": "2026-11-04", "added": 218, "updated": 0}
    assert len(entries(client, fy=2026)) == 218
    again = _import(client, data).json()
    assert (again["added"], again["updated"]) == (0, 0)
    # The DAILY REPORT sheet's station generation for October, month to date on the 30th.
    perf = client.get("/api/performance/2026-10-30").json()
    gen = next(r for r in perf["rows"] if r["key"] == "gen")
    assert gen["stn"]["month"] == pytest.approx(179.42)


# --- derived figures, config, health ----------------------------------------------------------

def test_performance(client, reader):
    client.put("/api/entries/2026-11-01", json={"u1Gen": 3.48, "u2Gen": 3.45})
    client.put("/api/entries/2026-11-02", json={"u1Gen": 3.56, "u2Gen": 3.72})
    reader(load_report(PAGE_1))
    upload(client)
    response = client.get("/api/performance/2026-11-03")
    assert response.status_code == 200, response.text
    perf = response.json()
    assert perf["date"] == "2026-11-03" and perf["fy"] == 2026 and perf["hasData"] is True
    gen = next(r for r in perf["rows"] if r["key"] == "gen")
    assert gen["stn"]["day"] == pytest.approx(7.16)
    assert gen["u1"]["month"] == pytest.approx(10.52)  # matches the page's progressive figure
    assert perf["missing"]["month"] == []
    assert perf["stocks"]["coal"] == {"value": 12246.51, "asOf": "2026-11-03", "source": "report"}
    assert client.get("/api/performance/2026-11-31").status_code == 400


def test_config(client):
    defaults = client.get("/api/config/2026").json()
    assert defaults["unitMw"] == 210 and len(defaults["monthlyTargets"]) == 12
    updated = client.put("/api/config/2026", json={"unitMw": 200, "bogus": 1}).json()
    assert updated["unitMw"] == 200 and "bogus" not in updated
    assert updated["monthlyTargets"] == defaults["monthlyTargets"]
    assert client.get("/api/config/2026").json()["unitMw"] == 200
    assert client.get("/api/config/2030").json()["monthlyTargets"] == {}


def test_health(client, reader, monkeypatch):
    monkeypatch.setattr(main.extract, "is_configured", lambda: False)
    body = client.get("/api/health").json()
    assert (body["ok"], body["database"], body["latestDate"], body["today"]) == (True, True, None, "2026-11-12")
    assert body["extraction"]["configured"] is False and body["extraction"]["model"] == extract.MODEL
    monkeypatch.setattr(main.extract, "is_configured", lambda: True)
    reader(load_report(PAGE_1))
    upload(client)
    body = client.get("/api/health").json()
    assert body["extraction"]["configured"] is True and body["latestDate"] == "2026-11-03"


def test_without_a_database(monkeypatch):
    monkeypatch.setattr(main, "db", None)
    monkeypatch.setattr(main, "client", None)
    monkeypatch.setattr(main, "MONGODB_URI", "")
    with TestClient(main.app) as c:  # starts anyway, so health can say what is wrong
        assert c.get("/api/health").json()["database"] is False
        response = c.get("/api/entries")
        assert response.status_code == 503
        assert "MONGODB_URI" in response.json()["detail"]


# --- page image retention --------------------------------------------------------------------

def run(coro):
    return asyncio.run(coro)


def test_images_expire_after_fifteen_days_via_a_ttl_index(client, reader):
    reader(load_report(PAGE_1))
    before = datetime.now(timezone.utc).replace(microsecond=0)
    body = upload(client).json()

    indexes = run(main.db["report_images"].index_information())
    ttl = indexes[main.IMAGE_TTL_INDEX]
    assert ttl["key"] == [("createdAt", 1)]
    assert ttl["expireAfterSeconds"] == 15 * 24 * 3600 == main.IMAGE_RETENTION_DAYS * 24 * 3600

    # The TTL index only acts on a real date, so createdAt must not be a string.
    image_doc = run(main.db["report_images"].find_one({"_id": body["id"]}))
    created = image_doc["createdAt"].replace(tzinfo=timezone.utc)
    assert isinstance(image_doc["createdAt"], datetime)
    assert before <= created <= datetime.now(timezone.utc)

    until = datetime.fromisoformat(body["imageUntil"])
    assert until - created == timedelta(days=15)
    assert client.get("/api/reports").json()[0]["imageUntil"] == body["imageUntil"]


def test_deleted_image_says_why(client, reader):
    reader(load_report(PAGE_1))
    report_id = upload(client).json()["id"]
    run(main.db["report_images"].delete_one({"_id": report_id}))  # what the TTL monitor does
    response = client.get(f"/api/reports/{report_id}/image")
    assert response.status_code == 404
    assert "kept for 15 days" in response.json()["detail"]
    # The report and the day's figures stay.
    assert client.get(f"/api/reports/{report_id}").status_code == 200
    assert entries(client, month="2026-11")[0]["reportId"] == report_id


def test_ttl_index_is_updated_when_retention_changes(monkeypatch):
    """An older deployment may have created the index with a different period."""

    class Collection:
        def __init__(self, info=None):
            self.info = info or {}

        async def create_index(self, *args, **kwargs):
            return "ok"

        async def create_indexes(self, models):
            return ["ok"] * len(models)

        async def index_information(self):
            return self.info

    class Database:
        def __init__(self):
            self.commands = []
            self.collections = {"report_images": Collection(
                {main.IMAGE_TTL_INDEX: {"key": [("createdAt", 1)], "expireAfterSeconds": 30 * 24 * 3600}})}

        def __getitem__(self, name):
            return self.collections.setdefault(name, Collection())

        async def command(self, *args, **kwargs):
            self.commands.append((args, kwargs))

    database = Database()
    monkeypatch.setattr(main, "db", database)
    run(main._ensure_indexes())
    assert database.commands == [(("collMod", "report_images"),
                                  {"index": {"name": main.IMAGE_TTL_INDEX, "expireAfterSeconds": 15 * 24 * 3600}})]
    run(main._ensure_indexes())  # once per database handle
    assert len(database.commands) == 1


# --- indexes and response size ----------------------------------------------------------------

def test_every_query_has_an_index(client):
    run(main._ensure_indexes())
    keys = {name: {tuple(i["key"]): i.get("unique", False)
                   for i in run(main.db[name].index_information()).values()}
            for name in ("entries", "reports", "config", "report_images", "users")}
    assert keys["entries"][(("date", 1),)] is True
    assert keys["reports"][(("id", 1),)] is True
    assert (("createdAt", -1),) in keys["reports"]
    assert (("dataDate", 1), ("createdAt", -1)) in keys["reports"]
    assert keys["config"][(("fy", 1),)] is True
    assert (("createdAt", 1),) in keys["report_images"]
    assert keys["users"][(("id", 1),)] is True and keys["users"][(("email", 1),)] is True
    assert (("sessions.hash", 1),) in keys["users"]


def test_reports_for_one_day(client, reader):
    reader(load_report(PAGE_1))
    body = upload(client).json()
    day = body["dataDate"]
    assert [r["id"] for r in client.get("/api/reports", params={"date": day}).json()] == [body["id"]]
    assert client.get("/api/reports", params={"date": "2026-10-01"}).json() == []
    assert client.get("/api/reports", params={"month": day[:7]}).json()[0]["id"] == body["id"]
    assert client.get("/api/reports", params={"date": "2026-13-01"}).status_code == 400


def test_json_is_gzipped_but_images_are_not(client, reader):
    for d in range(1, 29):
        client.put(f"/api/entries/2026-10-{d:02d}", json={"u1Gen": 4.5, "u2Gen": 4.6, "u1Remark": "running"})
    response = client.get("/api/entries", params={"month": "2026-10"}, headers={"Accept-Encoding": "gzip"})
    assert response.headers["content-encoding"] == "gzip"
    assert len(response.json()) == 28

    reader(load_report(PAGE_1))
    report_id = upload(client).json()["id"]
    image = client.get(f"/api/reports/{report_id}/image", headers={"Accept-Encoding": "gzip"})
    assert image.status_code == 200 and "content-encoding" not in image.headers
