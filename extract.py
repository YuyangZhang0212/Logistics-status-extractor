"""
Logistics status extractor.

Turns messy tracking text (17TRACK-style export, one parcel per block,
blocks separated by lines of '=') into a structured CSV table.

Division of work:
  Python : split blocks, read the platform label, check the AI's answers
  Gemini : read each block, pick the status, normalise number/carrier/time

Usage:
  python extract.py                                  # uses data/sample_input.txt
  python extract.py my_input.txt -o output/my_table.csv
  python extract.py --as-of 2025-12-23                # fix "today" for the sample data
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from alerts import alert_for, suggested_action

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
BATCH_SIZE = 10          # blocks sent to Gemini in one request
PAUSE_SECONDS = 4        # pause between requests (free-tier rate limits)
MAX_RETRIES = 3

CARRIERS = ["FedEx", "UPS", "USPS", "DHL", "Australia Post", "SF Express",
            "UniUni", "GOFO", "CTT Express", "Amazon Shipping"]
TIME_FMT = "%Y-%m-%d %H:%M:%S"


# ---------------------------------------------------------------------------
# 1. The output format we force the AI to follow (structured output)
# ---------------------------------------------------------------------------
class Status(str, Enum):
    info_received = "info_received"
    in_transit = "in_transit"
    out_for_delivery = "out_for_delivery"
    awaiting_pickup = "awaiting_pickup"
    delivered = "delivered"
    delivery_failed = "delivery_failed"
    exception = "exception"
    cancelled = "cancelled"
    not_found = "not_found"


class Parcel(BaseModel):
    block_id: int = Field(description="The block number given in the input.")
    tracking_number: str = Field(description="Main tracking number, uppercase, no spaces or hyphens. Empty string if absent.")
    carrier: str = Field(description="One of the allowed carrier names, or empty string if unknown.")
    latest_event_time: str = Field(description="Time of the most recent event as YYYY-MM-DD HH:MM:SS. Empty string if no events.")
    status: Status
    description: str = Field(description="Short English summary of the most recent event, including the location.")
    history_issue: str = Field(description="Short English note on any problem event BEFORE the latest event. Empty string if none.")


class ParcelList(BaseModel):
    parcels: List[Parcel]


# ---------------------------------------------------------------------------
# 2. Instructions for the AI (the business rules)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = f"""You extract parcel tracking information from messy text.
Each input block describes ONE parcel. Return one result per block, using the same block_id.

Rules:
- tracking_number: copy the main tracking number exactly as it appears, then make it uppercase
  and remove spaces and hyphens. If a block shows a second "transfer" number in brackets,
  use the first (main) number. If there is no tracking number, return "". Never invent one.
- carrier: use one of {CARRIERS}. Fix obvious typos (e.g. "Fedx" -> "FedEx") and translate
  Chinese names (e.g. 顺丰 -> "SF Express"). If several carriers are listed (e.g. "Amazon Shipping +
  Amazon MCF"), use the first. If the carrier line is missing, infer it only if the
  event text clearly names the carrier; otherwise return "".
- latest_event_time: find the event with the LATEST date and time, even if the events are not in
  order. Convert it to YYYY-MM-DD HH:MM:SS (24-hour). If there are no events, return "".
- status: decide from the LATEST event only. Ignore the "包裹状态" platform label, which may be
  outdated or too broad.
    info_received    = only shipping info / label created, not yet picked up
    in_transit       = picked up, moving between facilities, or delayed (e.g. weather) without a failed attempt
    out_for_delivery = on the vehicle / with the courier for delivery today
    awaiting_pickup  = waiting at a locker, post office or store for the receiver to collect
    delivered        = delivered or signed for
    delivery_failed  = a delivery attempt failed (no one home, notice left, incorrect address on attempt)
    exception        = customs hold, damage, lost, investigation to locate the package,
                       returning to sender, address problem without an attempt
    cancelled        = shipment cancelled or voided (in any language, e.g. Spanish "Envío anulado")
    not_found        = no tracking events at all (platform label may be "查询不到" or empty)
- description: one short English sentence about the latest event, including the location.
- history_issue: look at the events BEFORE the latest one. If any shows a problem (e.g. barcode
  unreadable, pickup exception, delivery exception, address problem), describe it briefly, even if the
  parcel later recovered. Return "" if there is none. Do not count the latest event here.
- Events may be in English, Chinese, Spanish or other languages.
- Ignore notes such as customer service remarks.
"""


# ---------------------------------------------------------------------------
# 3. Python helpers (no AI): split blocks, read labels, parse times
# ---------------------------------------------------------------------------
def split_blocks(text: str) -> List[str]:
    """Split the export into parcel blocks on lines made only of '=' signs."""
    parts = re.split(r"^\s*=+\s*$", text, flags=re.MULTILINE)
    return [p.strip() for p in parts if p.strip()]


def platform_status(block: str) -> str:
    """Copy the platform label (e.g. '运输途中 · 2天') as is."""
    m = re.search(r"包裹状态[:：]\s*(.+)", block)
    return m.group(1).strip() if m else ""


# Time formats seen in the exports. Add more here if new formats appear.
TIME_PATTERNS = [
    (r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", "%Y-%m-%d %H:%M:%S"),
    (r"\d{4}/\d{1,2}/\d{1,2} \d{1,2}:\d{2}", "%Y/%m/%d %H:%M"),
    (r"\d{1,2}/\d{1,2}/\d{4} \d{1,2}:\d{2} [AP]M", "%m/%d/%Y %I:%M %p"),
]


def rule_latest_time(block: str) -> Optional[datetime]:
    """Find the latest timestamp in a block using fixed patterns."""
    found = []
    for pattern, fmt in TIME_PATTERNS:
        for s in re.findall(pattern, block):
            try:
                found.append(datetime.strptime(s, fmt))
            except ValueError:
                pass
    return max(found) if found else None


def squash(s: str) -> str:
    """Uppercase and remove spaces/hyphens, for comparing tracking numbers."""
    return re.sub(r"[\s\-]", "", s).upper()


# ---------------------------------------------------------------------------
# 4. Rule checks on the AI's answer (catch obvious mistakes automatically)
# ---------------------------------------------------------------------------
def check(row: Dict, block: str) -> List[str]:
    problems = []

    # The number must really appear in the text -> catches invented numbers
    tn = row["tracking_number"]
    if tn and squash(tn) not in squash(block):
        problems.append("tracking number not found in source text")

    # Carrier must come from the allowed list
    if row["carrier"] and row["carrier"] not in CARRIERS:
        problems.append(f"unknown carrier '{row['carrier']}'")

    # Latest time must match what the rule-based parser finds
    expected = rule_latest_time(block)
    got = row["latest_event_time"]
    if expected and got != expected.strftime(TIME_FMT):
        problems.append(f"latest time differs from rule check ({expected.strftime(TIME_FMT)})")
    if not expected and got:
        problems.append("time given but no timestamp found by rule check")

    # A parcel with events cannot be 'not_found'
    if expected and row["status"] == "not_found":
        problems.append("status not_found but events exist")

    return problems


# ---------------------------------------------------------------------------
# 5. Call Gemini
# ---------------------------------------------------------------------------
def ask_gemini(client, model: str, batch: List[tuple]) -> List[Parcel]:
    """Send a batch of (block_id, text) pairs, get back a list of Parcel."""
    user_text = "\n\n".join(f"### Block {bid}\n{text}" for bid, text in batch)
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=ParcelList,
        temperature=0,
    )
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.models.generate_content(model=model, contents=user_text, config=config)
            return ParcelList.model_validate_json(resp.text).parcels
        except Exception as e:  # network error, rate limit, bad JSON...
            print(f"  attempt {attempt} failed: {e}")
            if attempt == MAX_RETRIES:
                raise
            time.sleep(10 * attempt)
    return []


def write_xlsx(rows: List[Dict], path: Path, followup: List[Dict], cs_cols: List[str]):
    """Excel copy with tracking numbers stored as text (no scientific notation).
    Sheet 1: all parcels. Sheet 2: customer service follow-up list."""
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "parcels"
    headers = list(rows[0].keys())
    ws.append(headers)
    fills = {"high": PatternFill("solid", fgColor="F8CBAD"), "low": PatternFill("solid", fgColor="FFF2CC")}
    tn_col = headers.index("tracking_number") + 1
    for r in rows:
        ws.append([r[h] for h in headers])
        ws.cell(row=ws.max_row, column=tn_col).number_format = "@"  # text format
        if r["alert_level"] in fills:
            for c in ws[ws.max_row]:
                c.fill = fills[r["alert_level"]]
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    cs = wb.create_sheet("customer service follow-up")
    cs.append(cs_cols)
    for r in followup:
        cs.append([r[h] for h in cs_cols])
        cs.cell(row=cs.max_row, column=1).number_format = "@"
    cs.freeze_panes = "A2"
    wb.save(path)


# ---------------------------------------------------------------------------
# 6. Main pipeline
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Turn messy tracking text into a table.")
    parser.add_argument("input", nargs="?", default="data/sample_input.txt")
    parser.add_argument("-o", "--output", default="output/structured.csv")
    parser.add_argument("--as-of", help="'Today' for the stuck rule, YYYY-MM-DD (default: now)")
    parser.add_argument("--stuck-days", type=int, default=5, help="Days without update before alert")
    args = parser.parse_args()
    as_of = datetime.strptime(args.as_of, "%Y-%m-%d") if args.as_of else datetime.now()

    load_dotenv()  # reads GEMINI_API_KEY (and optional GEMINI_MODEL) from .env
    if not os.getenv("GEMINI_API_KEY"):
        sys.exit("GEMINI_API_KEY not set. Copy .env.example to .env and add your key.")
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    client = genai.Client()  # picks up GEMINI_API_KEY automatically

    text = Path(args.input).read_text(encoding="utf-8")
    blocks = split_blocks(text)
    print(f"Found {len(blocks)} parcel blocks in {args.input}. Model: {model}")

    numbered = list(enumerate(blocks, start=1))
    answers: Dict[int, Parcel] = {}
    raw_log = []
    for start in range(0, len(numbered), BATCH_SIZE):
        batch = numbered[start:start + BATCH_SIZE]
        print(f"Processing blocks {batch[0][0]}-{batch[-1][0]} ...")
        try:
            for p in ask_gemini(client, model, batch):
                answers[p.block_id] = p
                raw_log.append(p.model_dump(mode="json"))
        except Exception as e:
            print(f"  batch skipped after retries: {e}")
        time.sleep(PAUSE_SECONDS)

    rows = []
    for bid, block in numbered:
        p = answers.get(bid)
        if p is None:
            row = dict(block_id=bid, tracking_number="", carrier="", latest_event_time="",
                       status="", description="", history_issue="")
            problems = ["no answer from AI"]
        else:
            row = dict(block_id=bid, tracking_number=p.tracking_number, carrier=p.carrier,
                       latest_event_time=p.latest_event_time, status=p.status.value,
                       description=p.description, history_issue=p.history_issue)
            problems = check(row, block)
        row["platform_status"] = platform_status(block)
        level, reason = alert_for(row["status"], row["latest_event_time"],
                                  bool(row["history_issue"]), as_of, args.stuck_days)
        row["alert_level"] = level
        row["alert_reason"] = reason
        row["action"] = suggested_action(row["status"], reason) if level == "high" else ""
        row["needs_review"] = "yes" if problems else "no"
        row["review_reason"] = "; ".join(problems)
        rows.append(row)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig so Excel on Windows shows Chinese characters correctly
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    with open(out.with_name(out.stem + "_raw.jsonl"), "w", encoding="utf-8") as f:
        for item in raw_log:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    # Follow-up list for customer service: high alerts only
    followup = [r for r in rows if r["alert_level"] == "high"]
    cs_cols = ["tracking_number", "carrier", "status", "latest_event_time",
               "description", "alert_reason", "action"]
    cs_path = out.with_name(out.stem + "_followup.csv")
    with open(cs_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=cs_cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(followup)

    write_xlsx(rows, out.with_suffix(".xlsx"), followup, cs_cols)

    flagged = sum(r["needs_review"] == "yes" for r in rows)
    high = sum(r["alert_level"] == "high" for r in rows)
    low = sum(r["alert_level"] == "low" for r in rows)
    print(f"Done. Wrote {len(rows)} rows to {out} and {out.with_suffix('.xlsx')}")
    print(f"Needs review (AI may be wrong): {flagged}")
    print(f"Alerts (parcel needs follow-up): high {high}, low {low}  [as of {as_of:%Y-%m-%d}]")
    print(f"Customer service follow-up list: {cs_path} ({len(followup)} parcels)")


if __name__ == "__main__":
    main()
