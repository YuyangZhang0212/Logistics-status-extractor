# Logistics Status Extractor

Turns messy parcel tracking exports into a clean table, flags parcels that need follow-up, and measures how accurate the AI is.

**Python + Gemini API (structured JSON output) + rule-based checks + evaluation against an answer key.**

## The problem

I handled tracking updates for large batches of parcels. The tracking tool exports text like this, one block per parcel:

```
单号：7712XXXXXXXX
物流商：FedEx
包裹状态：到达待取 · 2天
国家：美国->美国
2025-12-20 05:30:00 On FedEx vehicle for delivery SPRINGFIELD, MA, US
2025-12-20 04:58:00 At local FedEx facility SPRINGFIELD, MA, US
==========================================
```

I used to paste these into an AI chat and then into Excel by hand to find which parcels had problems. That was slow, inconsistent between batches, and gave no way to tell how often the AI got it wrong.

Real exports are messy in many ways. Events can be out of order. Carriers word things differently ("Delivery exception", "Notice Left", "Envío anulado"). Text may be in English, Chinese or Spanish. Lines can be missing. The platform's own status label can also be too coarse or out of date.

## What it does

```
messy .txt export
   │
   ├─ Python: split into parcel blocks, read the platform label
   │
   ├─ Gemini: extract fields and classify status → JSON that must match a fixed schema
   │
   ├─ Python rule checks: is the tracking number really in the text? does the latest time
   │                      match a rule-based parser? → needs_review flag
   │
   ├─ Python alert rules: problem status, or no update for 5+ days → alert + suggested action
   │
   └─ Outputs: full table (.csv / .xlsx) + customer service follow-up list
```

Output columns: `tracking_number`, `carrier`, `latest_event_time`, `status` (one of 9 fixed values), `description`, `history_issue`, `platform_status`, `needs_review`, `alert_level`, `alert_reason`, `action`.

Design choices:

- **Status comes from the latest event, not the platform label.** The label "到达待取" covers both "out for delivery" and "awaiting pickup", so I split them.
- **AI only does what needs language understanding.** Splitting blocks, parsing times, alert rules and suggested actions are plain Python, so they are deterministic, free to run and easy to change.
- **Two separate flags.** `needs_review` means "the AI might be wrong" (data quality). `alert_level` means "this parcel needs action" (business). They answer different questions for different people.
- **Stuck threshold is 5 days.** Carriers often don't scan over weekends.
- **Excel output stores tracking numbers as text**, so long numbers don't turn into scientific notation.

## Test data

`data/sample_input.txt` has **48 fictional parcels**. No real customer data is used. 20 are clean cases covering every status. 28 are deliberately difficult: events out of order, numbers with spaces, missing carrier or tracking number lines, Chinese-only or mixed-language events, US time formats, platform labels that contradict the events, carrier typos, noise lines, transfer numbers, duplicate events, a year boundary, a Spanish cancellation, recovered exceptions (e.g. barcode replaced) and a parcel stuck for 6 days. Some of these patterns come from real exception reports I've worked with.

`data/labels.csv` is the answer key. `make_sample_data.py` generates both files. Latest event times in the answer key are calculated by code, not typed. Status labels were drafted with AI assistance against rules I set, and I made the final call on disputed cases.

## Results

Model: `gemini-3.5-flash-lite`, temperature 0, 48 parcels, run on 3 Nov 2026. Full output is in [`output/`](output/).

| Field | Run |
|---|---|
| tracking_number | 48/48 |
| carrier | 48/48 |
| latest_event_time | 48/48 |
| status | 47/48 |
| has_history_issue | 48/48 |
| alert_level | 48/48 |
| **All fields correct** |  **47/48 (97.9%)** |

\* Scored against the original answer key.

The per-case breakdown is in [`output/eval_summary.md`](output/eval_summary.md) and every wrong field is listed in [`output/eval_errors.csv`](output/eval_errors.csv).

### Error analysis

| Block | Event text | Expected | Run | Cause |
|---|---|---|---|---|
| 20 | Onboard for delivery → "Unable to deliver - incorrect or incomplete address" | delivery_failed |  **exception** | Ambiguous wording |


What I learned from this:

1. **Carrier wording vs internal categories is the weak spot.** A failed delivery attempt caused by a wrong address sits on the line between delivery_failed and exception. Carriers make it worse, e.g. FedEx calls a failed attempt a "Delivery exception".
2. **Results vary between runs on ambiguous cases, even at temperature 0.** In an earlier test run, block 20 was correct and block 33 (the same situation, worded "Delivery exception Incorrect address") was wrong. The other 46 parcels were correct both times.
3. **Evaluation also found a mistake in my answer key.** In that earlier run, blocks 20 and 33 turned out to be labelled differently even though they describe the same situation. I corrected block 20 to delivery_failed before the final run.
4. **Impact was limited.** Both statuses are high alerts, so the parcel still reached the customer service list. Only the suggested action differed.
5. **The rule checks did not catch this error.** They catch objective mistakes, such as invented tracking numbers or wrong times (tested with simulated errors), but they cannot judge a classification. Status errors need an answer key or human spot checks.

## Limitations

- Small, fictional dataset (48 parcels) that I designed. Real accuracy on live data will differ.
- Answer-key status labels were AI-drafted and are only as good as my review.
- `description` is free text and was spot-checked, not scored.
- Results vary slightly between runs on ambiguous cases.
- Suggested actions depend on the status, so a misclassification within the high group can suggest the wrong next step.
- Runs on Python 3.9 (end of life), which installs an older `google-genai` version. Python 3.11+ is recommended.
- No live trigger yet. Possible next step: an n8n workflow that runs the script on each new export and emails the follow-up list to customer service.

## How to run

```powershell
pip install -r requirements.txt
copy .env.example .env        # then paste your own Gemini API key into .env
python make_sample_data.py    # regenerate fictional test data + answer key
python extract.py --as-of 2025-12-23   # sample data is from Dec 2025
python evaluate.py
```

For your own export: `python extract.py my_export.txt -o output/my_table.csv`. Without `--as-of`, "today" is the current date.

The API key is read from `.env`, which is excluded by `.gitignore` and never committed.

## Files

| File | Purpose |
|---|---|
| `extract.py` | Main tool: split → Gemini → checks → alerts → CSV/XLSX |
| `alerts.py` | Alert rules and suggested actions (shared with the answer key) |
| `evaluate.py` | Compares output with the answer key, writes accuracy and error list |
| `make_sample_data.py` | Generates fictional test data and the answer key |
| `data/` | Sample input and answer key |
| `output/` | Results from the final run |

## My role

I designed the solution: the scope, the output fields and status categories, the business rules (status from the latest event, 5-day stuck threshold, high/low alerts, customer service actions), and which messy cases to test, based on my working experience. I ran every step, reviewed the outputs, decided how to resolve disputed labels and interpreted the errors.

Code was written with AI assistance.
