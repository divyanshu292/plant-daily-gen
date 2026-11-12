"""Run the API locally without MongoDB or a Gemini key.

    cd backend && .venv/bin/python dev_server.py

- The database lives in memory and is seeded from the plant workbook in the
  project root, so month and year figures are realistic.
- If GEMINI_API_KEY is not set, report images are not really read: the two
  sample pages in the project root return their hand-checked transcriptions
  (recognised by image shape). Any other portrait image returns a page with one
  wrong digit, to exercise the needs-review path, and a landscape image is
  rejected as not being a report.

Nothing here is used in production; main.py is the real entry point.
"""

import asyncio
import json
import os
from pathlib import Path

import uvicorn
from mongomock_motor import AsyncMongoMockClient

os.environ.setdefault("MONGODB_URI", "")
import main  # noqa: E402
import extract  # noqa: E402
import workbook_import  # noqa: E402
from report_schema import DailySystemReport  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "tests" / "fixtures"

main.db = AsyncMongoMockClient()["ttps_dev"]


def _fixture(name: str) -> DailySystemReport:
    return DailySystemReport.model_validate(json.loads((FIXTURES / name).read_text()))


async def fake_extract(image, recheck=None):
    """Stand-in for the vision call, chosen by the shape of the uploaded image."""
    ratio = image.width / image.height
    await asyncio.sleep(1.5)  # a real read takes a while; keep the UI honest
    if ratio > 1.2:  # landscape: not a report page
        report = _fixture("report_2026-11-04.json")
        report.is_daily_system_report = False
    elif 0.76 <= ratio <= 0.80:  # the sample screenshot (1414 x 1810)
        report = _fixture("report_2026-11-04.json")
    elif 0.68 <= ratio <= 0.72:  # the sample phone photo (1119 x 1599)
        report = _fixture("report_2026-11-11.json")
    else:  # any other portrait image: a page with one misread digit
        report = _fixture("report_2026-11-04.json")
        report.r04_gen.unit1 = "3.43"  # totals and PLF no longer agree
    return extract.Extraction(report=report, model="dev-fixture", usage={"inputTokens": 0, "outputTokens": 0})


if not extract.is_configured():
    main.extract.extract_report = fake_extract


async def seed() -> None:
    books = sorted(ROOT.glob("TTPS DAILY GEN DATA*.xlsx"))
    if not books:
        print("dev: no workbook found in the project root, starting empty")
        return
    book = workbook_import.read_workbook(books[-1].read_bytes())
    for row in book["entries"]:
        await main.db["entries"].insert_one({**row, "source": "workbook"})
    if book["config"]:
        await main.db["config"].insert_one({"fy": book["fy"], **book["config"]})
    print(f"dev: seeded {len(book['entries'])} days from {books[-1].name}")


if __name__ == "__main__":
    asyncio.run(seed())
    uvicorn.run(main.app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
