"""
Evaluate the extractor against the hand-checked answer key.

Compares output/structured.csv with data/labels.csv field by field and writes:
  output/eval_summary.md   - accuracy table (paste into README)
  output/eval_errors.csv   - every wrong field, for error analysis

Usage:
  python evaluate.py
  python evaluate.py --pred output/structured.csv --labels data/labels.csv
"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path

# Fields we score. description is free text, so it is checked by hand instead.
FIELDS = ["tracking_number", "carrier", "latest_event_time", "status",
          "has_history_issue", "alert_level"]


def load(path, encoding):
    with open(path, encoding=encoding) as f:
        return {r["block_id"]: r for r in csv.DictReader(f)}


def predicted_value(row, field):
    """Turn the tool's output into the same form as the answer key."""
    if field == "has_history_issue":
        return "yes" if row.get("history_issue", "").strip() else "no"
    return row.get(field, "").strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pred", default="output/structured.csv")
    parser.add_argument("--labels", default="data/labels.csv")
    parser.add_argument("--out-dir", default="output")
    args = parser.parse_args()

    labels = load(args.labels, "utf-8")
    preds = load(args.pred, "utf-8-sig")

    correct = defaultdict(int)
    by_case = defaultdict(lambda: [0, 0])  # case_type -> [blocks fully correct, total]
    errors = []
    fully_correct = 0
    error_blocks, caught_blocks = 0, 0

    for bid, gold in labels.items():
        pred = preds.get(bid, {})
        block_ok = True
        for field in FIELDS:
            expected = gold[field].strip()
            got = predicted_value(pred, field)
            if got == expected:
                correct[field] += 1
            else:
                block_ok = False
                errors.append({
                    "block_id": bid,
                    "case_type": gold["case_type"],
                    "field": field,
                    "expected": expected,
                    "got": got,
                    "needs_review": pred.get("needs_review", ""),
                    "ai_description": pred.get("description", ""),
                    "ai_history_issue": pred.get("history_issue", ""),
                })
        fully_correct += block_ok
        by_case[gold["case_type"]][0] += block_ok
        by_case[gold["case_type"]][1] += 1
        if not block_ok:
            error_blocks += 1
            caught_blocks += pred.get("needs_review") == "yes"

    n = len(labels)
    lines = ["## Accuracy by field", "",
             f"Blocks evaluated: {n}", "",
             "| Field | Correct | Accuracy |", "|---|---|---|"]
    for field in FIELDS:
        lines.append(f"| {field} | {correct[field]}/{n} | {correct[field] / n:.1%} |")
    lines.append(f"| **All fields correct** | {fully_correct}/{n} | {fully_correct / n:.1%} |")

    lines += ["", "## Blocks fully correct by case type", "",
              "| Case type | Fully correct |", "|---|---|"]
    for case, (ok, total) in sorted(by_case.items()):
        lines.append(f"| {case} | {ok}/{total} |")

    lines += ["", "## Did the automatic review flag catch the errors?", "",
              f"Blocks with at least one error: {error_blocks}  ",
              f"Of those, flagged needs_review = yes: {caught_blocks}"]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(exist_ok=True)
    (out_dir / "eval_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    with open(out_dir / "eval_errors.csv", "w", newline="", encoding="utf-8-sig") as f:
        fieldnames = ["block_id", "case_type", "field", "expected", "got",
                      "needs_review", "ai_description", "ai_history_issue"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(errors)

    print("\n".join(lines))
    print(f"\nWrote {out_dir / 'eval_summary.md'} and {out_dir / 'eval_errors.csv'} ({len(errors)} wrong fields)")


if __name__ == "__main__":
    main()
