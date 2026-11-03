## Accuracy by field

Blocks evaluated: 48

| Field | Correct | Accuracy |
|---|---|---|
| tracking_number | 48/48 | 100.0% |
| carrier | 48/48 | 100.0% |
| latest_event_time | 48/48 | 100.0% |
| status | 47/48 | 97.9% |
| has_history_issue | 48/48 | 100.0% |
| alert_level | 48/48 | 100.0% |
| **All fields correct** | 47/48 | 97.9% |

## Blocks fully correct by case type

| Case type | Fully correct |
|---|---|
| ambiguous_delay | 1/1 |
| cancelled_spanish | 1/1 |
| carrier_typo | 1/1 |
| chinese_text | 1/1 |
| clean | 18/19 |
| duplicate_events | 1/1 |
| empty_status | 1/1 |
| investigation | 1/1 |
| midnight_time | 1/1 |
| missing_carrier_inferable | 1/1 |
| missing_carrier_unknown | 1/1 |
| missing_number | 1/1 |
| mixed_language | 1/1 |
| no_events | 2/2 |
| noise_lines | 1/1 |
| number_format | 2/2 |
| out_of_order | 2/2 |
| platform_conflict | 2/2 |
| recovered_history | 3/3 |
| stuck | 1/1 |
| time_format | 2/2 |
| two_numbers | 1/1 |
| year_boundary | 1/1 |

## Did the automatic review flag catch the errors?

Blocks with at least one error: 1  
Of those, flagged needs_review = yes: 0
