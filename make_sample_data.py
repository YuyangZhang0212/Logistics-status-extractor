"""
Generate fictional logistics tracking text and the matching answer key.

All tracking numbers, events and notes are made up. No real customer data.

Outputs:
  data/sample_input.txt  - messy tracking blocks (17TRACK-style export format)
  data/labels.csv        - the expected answer for each block (answer key)

Each case lists its events with an ISO timestamp, so the "latest event time"
in the answer key is calculated, not typed by hand. The displayed timestamp
format can differ per case to simulate messy input.
"""

import csv
import random
from datetime import datetime
from pathlib import Path

from alerts import alert_for

ISO = "%Y-%m-%d %H:%M:%S"

# Each case: what the block looks like + what the correct answer is.
# Keys:
#   num        tracking number as it appears in the text (None = line missing)
#   num_true   normalised tracking number for the answer key ("" = unknown)
#   carrier    carrier line as it appears (None = line missing)
#   carrier_true  normalised carrier for the answer key ("" = unknown)
#   platform   platform status label (17TRACK style)
#   route      country line
#   events     list of (ISO time, event text), any order
#   status     correct status from the fixed list
#   case_type  tag used later in error analysis
#   fmt        optional display format for timestamps
#   shuffle    show events out of order
#   extra      extra noise lines
CASES = [
    # ---------- Clean cases ----------
    dict(num="771245803101", carrier="FedEx", platform="运输途中 · 2天", route="美国->美国",
         events=[("2025-12-18 13:08:00", "Shipment information sent to FedEx US"),
                 ("2025-12-19 00:00:00", "Picked up ALLENTOWN, PA, US"),
                 ("2025-12-19 18:40:00", "Arrived at FedEx location ALLENTOWN, PA, US"),
                 ("2025-12-19 21:05:12", "Left FedEx origin facility ALLENTOWN, PA, US")],
         status="in_transit", case_type="clean"),
    dict(num="771245803102", carrier="FedEx", platform="到达待取 · 2天", route="美国->美国",
         events=[("2025-12-19 21:10:00", "Left FedEx origin facility ALLENTOWN, PA, US"),
                 ("2025-12-20 04:58:00", "At local FedEx facility SPRINGFIELD, MA, US"),
                 ("2025-12-20 05:30:00", "On FedEx vehicle for delivery SPRINGFIELD, MA, US")],
         status="out_for_delivery", case_type="clean"),
    dict(num="771245803103", carrier="FedEx", platform="成功签收 · 3天", route="美国->美国",
         events=[("2025-12-20 05:30:00", "On FedEx vehicle for delivery SPRINGFIELD, MA, US"),
                 ("2025-12-20 13:47:00", "Delivered SPRINGFIELD, MA, US")],
         status="delivered", case_type="clean"),
    dict(num="1Z7Q4W2E0312345671", carrier="UPS", platform="运输途中 · 3天", route="美国->美国",
         events=[("2025-12-17 09:00:00", "Shipper created a label, UPS has not received the package yet."),
                 ("2025-12-18 19:22:00", "Arrived at Facility LOUISVILLE, KY, US"),
                 ("2025-12-19 02:41:00", "Departed from Facility LOUISVILLE, KY, US")],
         status="in_transit", case_type="clean"),
    dict(num="1Z7Q4W2E0312345672", carrier="UPS", platform="成功签收 · 4天", route="美国->美国",
         events=[("2025-12-20 08:15:00", "Out For Delivery Today COLUMBUS, OH, US"),
                 ("2025-12-20 15:02:00", "DELIVERED Front Door COLUMBUS, OH, US")],
         status="delivered", case_type="clean"),
    dict(num="9400111899223300112201", carrier="USPS", platform="到达待取 · 3天", route="美国->美国",
         events=[("2025-12-21 05:50:00", "Arrived at Post Office BROOKLYN, NY 11201"),
                 ("2025-12-21 07:12:00", "Out for Delivery BROOKLYN, NY 11201")],
         status="out_for_delivery", case_type="clean"),
    dict(num="9400111899223300112202", carrier="USPS", platform="成功签收 · 4天", route="美国->美国",
         events=[("2025-12-21 07:12:00", "Out for Delivery QUEENS, NY 11101"),
                 ("2025-12-21 12:33:00", "Delivered, In/At Mailbox QUEENS, NY 11101")],
         status="delivered", case_type="clean"),
    dict(num="4829103301", carrier="DHL", platform="运输途中 · 5天", route="德国->澳大利亚",
         events=[("2025-12-16 10:00:00", "Shipment picked up LEIPZIG - GERMANY"),
                 ("2025-12-17 03:20:00", "Departed Facility in LEIPZIG - GERMANY"),
                 ("2025-12-18 22:45:00", "Shipment is in transit to destination SINGAPORE")],
         status="in_transit", case_type="clean"),
    dict(num="4829103302", carrier="DHL", platform="成功签收 · 6天", route="德国->澳大利亚",
         events=[("2025-12-21 07:40:00", "Shipment is out with courier for delivery SYDNEY - AUSTRALIA"),
                 ("2025-12-21 11:05:00", "Delivered - Signed for by: J SMITH SYDNEY - AUSTRALIA")],
         status="delivered", case_type="clean"),
    dict(num="33QWE5501020001", carrier="Australia Post", platform="运输途中 · 2天", route="澳大利亚->澳大利亚",
         events=[("2025-12-19 16:20:00", "Shipping information received by Australia Post"),
                 ("2025-12-20 09:10:00", "Received and ready for processing CHULLORA NSW"),
                 ("2025-12-20 23:35:00", "In transit to next facility in SYDNEY NSW")],
         status="in_transit", case_type="clean"),
    dict(num="33QWE5501020002", carrier="Australia Post", platform="到达待取 · 3天", route="澳大利亚->澳大利亚",
         events=[("2025-12-21 06:30:00", "Onboard for delivery PARRAMATTA NSW"),
                 ("2025-12-21 10:18:00", "Awaiting collection at Parcel Locker PARRAMATTA NSW")],
         status="awaiting_pickup", case_type="clean"),
    dict(num="771245803112", carrier="FedEx", platform="到达待取 · 4天", route="美国->美国",
         events=[("2025-12-22 08:00:00", "At local FedEx facility AUSTIN, TX, US"),
                 ("2025-12-22 11:26:00", "Ready for pickup at FedEx retail location AUSTIN, TX, US")],
         status="awaiting_pickup", case_type="clean"),
    dict(num="771245803113", carrier="FedEx", platform="运输途中 · 1天", route="美国->美国",
         events=[("2025-12-22 14:02:00", "Shipment information sent to FedEx US")],
         status="info_received", case_type="clean"),
    dict(num="771245803114", carrier="FedEx", platform="查询不到", route="美国->美国",
         events=[],
         status="not_found", case_type="no_events"),
    dict(num="771245803115", carrier="FedEx", platform="投递失败 · 5天", route="美国->美国",
         events=[("2025-12-22 06:10:00", "On FedEx vehicle for delivery DENVER, CO, US"),
                 ("2025-12-22 17:44:00", "Delivery exception Customer not available or business closed DENVER, CO, US")],
         status="delivery_failed", case_type="clean"),
    dict(num="9400111899223300112216", carrier="USPS", platform="投递失败 · 5天", route="美国->美国",
         events=[("2025-12-22 07:00:00", "Out for Delivery BOSTON, MA 02118"),
                 ("2025-12-22 16:05:00", "Notice Left (No Authorized Recipient Available) BOSTON, MA 02118")],
         status="delivery_failed", case_type="clean"),
    dict(num="4829103317", carrier="DHL", platform="可能异常 · 7天", route="中国->澳大利亚",
         events=[("2025-12-18 05:00:00", "Arrived at DHL Sort Facility SYDNEY - AUSTRALIA"),
                 ("2025-12-18 09:32:00", "Clearance delay - Import SYDNEY - AUSTRALIA")],
         status="exception", case_type="clean"),
    dict(num="1Z7Q4W2E0312345688", carrier="UPS", platform="可能异常 · 9天", route="美国->美国",
         events=[("2025-12-19 10:00:00", "The receiver has moved. We're attempting to obtain a new delivery address."),
                 ("2025-12-20 13:15:00", "Returning to sender: The receiver has moved PHOENIX, AZ, US")],
         status="exception", case_type="clean", history=True),
    dict(num="771245803119", carrier="FedEx", platform="可能异常 · 6天", route="美国->美国",
         events=[("2025-12-20 02:00:00", "Arrived at FedEx hub MEMPHIS, TN, US"),
                 ("2025-12-20 04:50:00", "Shipment exception Package damaged MEMPHIS, TN, US")],
         status="exception", case_type="clean"),
    dict(num="33QWE5501020020", carrier="Australia Post", platform="可能异常 · 6天", route="澳大利亚->澳大利亚",
         events=[("2025-12-21 07:00:00", "Onboard for delivery BRUNSWICK VIC"),
                 ("2025-12-21 13:40:00", "Unable to deliver - incorrect or incomplete address BRUNSWICK VIC")],
         status="delivery_failed", case_type="clean"),

    # ---------- Messy cases ----------
    dict(num="771245803121", carrier="FedEx", platform="成功签收 · 4天", route="美国->美国", shuffle=True,
         events=[("2025-12-19 21:00:00", "Left FedEx origin facility RENO, NV, US"),
                 ("2025-12-20 06:15:00", "On FedEx vehicle for delivery SACRAMENTO, CA, US"),
                 ("2025-12-20 14:22:00", "Delivered SACRAMENTO, CA, US"),
                 ("2025-12-20 03:40:00", "At local FedEx facility SACRAMENTO, CA, US")],
         status="delivered", case_type="out_of_order"),
    dict(num="1Z7Q4W2E0312345622", carrier="UPS", platform="到达待取 · 3天", route="美国->美国", shuffle=True,
         events=[("2025-12-21 01:10:00", "Arrived at Facility DALLAS, TX, US"),
                 ("2025-12-21 07:55:00", "Out For Delivery Today DALLAS, TX, US"),
                 ("2025-12-20 18:30:00", "Departed from Facility HOUSTON, TX, US")],
         status="out_for_delivery", case_type="out_of_order"),
    dict(num="7712 4580 3123", num_true="771245803123", carrier="FedEx", platform="运输途中 · 2天", route="美国->美国",
         events=[("2025-12-21 09:00:00", "Picked up SEATTLE, WA, US"),
                 ("2025-12-21 20:12:00", "Left FedEx origin facility SEATTLE, WA, US")],
         status="in_transit", case_type="number_format"),
    dict(num="1z7q4w2e-0312-3456-24", num_true="1Z7Q4W2E0312345624", carrier="UPS", platform="运输途中 · 2天", route="美国->美国",
         events=[("2025-12-21 12:00:00", "Arrived at Facility ATLANTA, GA, US")],
         status="in_transit", case_type="number_format"),
    dict(num="771245803125", carrier=None, carrier_true="FedEx", platform="运输途中 · 3天", route="美国->美国",
         events=[("2025-12-21 10:30:00", "Arrived at FedEx location NEWARK, NJ, US"),
                 ("2025-12-21 22:05:00", "Departed FedEx location NEWARK, NJ, US")],
         status="in_transit", case_type="missing_carrier_inferable"),
    dict(num="550012873326", carrier=None, carrier_true="", platform="运输途中 · 3天", route="美国->美国",
         events=[("2025-12-21 10:30:00", "Arrived at sort facility"),
                 ("2025-12-21 22:05:00", "Departed sort facility")],
         status="in_transit", case_type="missing_carrier_unknown"),
    dict(num=None, num_true="", carrier="FedEx", platform="成功签收 · 3天", route="美国->美国",
         events=[("2025-12-22 07:00:00", "On FedEx vehicle for delivery ORLANDO, FL, US"),
                 ("2025-12-22 12:10:00", "Delivered ORLANDO, FL, US")],
         status="delivered", case_type="missing_number"),
    dict(num="SF1408823300128", carrier="顺丰速运", carrier_true="SF Express", platform="成功签收 · 2天", route="中国->中国",
         events=[("2025-12-20 08:12:00", "【深圳市】快件已发车，下一站【深圳宝安中转场】"),
                 ("2025-12-21 09:30:00", "【深圳市】快件交给快递员，正在派送途中"),
                 ("2025-12-21 14:05:00", "【深圳市】已签收，签收人：前台代收")],
         status="delivered", case_type="chinese_text"),
    dict(num="33QWE5501020029", carrier="Australia Post", platform="到达待取 · 2天", route="澳大利亚->澳大利亚",
         events=[("2025-12-21 02:15:00", "已到达 MELBOURNE VIC 转运中心 Arrived at facility"),
                 ("2025-12-21 09:12:00", "派送中 Onboard for delivery MELBOURNE VIC")],
         status="out_for_delivery", case_type="mixed_language"),
    dict(num="1Z7Q4W2E0312345630", carrier="UPS", platform="成功签收 · 3天", route="美国->美国",
         fmt="%m/%d/%Y %I:%M %p",
         events=[("2025-12-21 08:05:00", "Out For Delivery Today CHARLOTTE, NC, US"),
                 ("2025-12-21 15:45:00", "DELIVERED Front Desk/Reception CHARLOTTE, NC, US")],
         status="delivered", case_type="time_format"),
    dict(num="4829103331", carrier="DHL", platform="运输途中 · 4天", route="英国->澳大利亚",
         fmt="%Y/%m/%d %H:%M",
         events=[("2025-12-21 23:50:00", "Departed Facility in EAST MIDLANDS - UK"),
                 ("2025-12-22 08:05:00", "Arrived at DHL Sort Facility DUBAI - UAE")],
         status="in_transit", case_type="time_format"),
    dict(num="771245803132", carrier="FedEx", platform="运输途中 · 3天", route="美国->美国",
         events=[("2025-12-22 06:40:00", "On FedEx vehicle for delivery PORTLAND, OR, US"),
                 ("2025-12-22 11:58:00", "Delivered PORTLAND, OR, US")],
         status="delivered", case_type="platform_conflict"),
    dict(num="771245803133", carrier="FedEx", platform="成功签收 · 4天", route="美国->美国",
         events=[("2025-12-22 06:40:00", "On FedEx vehicle for delivery SALEM, OR, US"),
                 ("2025-12-22 18:20:00", "Delivery exception Incorrect address SALEM, OR, US")],
         status="delivery_failed", case_type="platform_conflict"),
    dict(num="771245803134", carrier="Fedx", carrier_true="FedEx", platform="运输途中 · 2天", route="美国->美国",
         events=[("2025-12-22 10:10:00", "Arrived at FedEx location OAKLAND, CA, US")],
         status="in_transit", case_type="carrier_typo"),
    dict(num="771245803135", carrier="FedEx", platform="运输途中 · 6天", route="美国->美国",
         extra=["备注：客户已催单 3 次，请优先处理", "客服：Amy（虚构）"],
         events=[("2025-12-20 22:00:00", "Departed FedEx hub MEMPHIS, TN, US"),
                 ("2025-12-21 15:30:00", "In transit NASHVILLE, TN, US")],
         status="in_transit", case_type="noise_lines"),
    dict(num="771245803136（转单号：9400111899223300112236）", num_true="771245803136",
         carrier="FedEx", platform="运输途中 · 5天", route="美国->美国",
         events=[("2025-12-21 08:00:00", "Departed FedEx hub INDIANAPOLIS, IN, US"),
                 ("2025-12-22 09:20:00", "Tendered to USPS for final delivery TOLEDO, OH, US")],
         status="in_transit", case_type="two_numbers"),
    dict(num="1Z7Q4W2E0312345637", carrier="UPS", platform="成功签收 · 3天", route="美国->美国",
         events=[("2025-12-22 08:00:00", "Out For Delivery Today TAMPA, FL, US"),
                 ("2025-12-22 13:13:00", "DELIVERED Front Door TAMPA, FL, US"),
                 ("2025-12-22 13:13:00", "DELIVERED Front Door TAMPA, FL, US")],
         status="delivered", case_type="duplicate_events"),
    dict(num="771245803138", carrier="FedEx", platform="可能异常 · 5天", route="美国->美国",
         events=[("2025-12-21 23:00:00", "Departed FedEx hub MEMPHIS, TN, US"),
                 ("2025-12-22 07:30:00", "Delay Severe weather conditions have delayed delivery MINNEAPOLIS, MN, US")],
         status="in_transit", case_type="ambiguous_delay"),
    dict(num="771245803139", carrier="FedEx", platform="运输途中 · 1天", route="美国->美国",
         events=[("2025-12-22 13:08:00", "Shipment information sent to FedEx US"),
                 ("2025-12-23 00:00:00", "Picked up TRENTON, NJ, US")],
         status="in_transit", case_type="midnight_time"),
    dict(num="4829103340", carrier="DHL", platform="成功签收 · 5天", route="新西兰->澳大利亚", shuffle=True,
         events=[("2025-12-31 23:50:00", "Shipment is out with courier for delivery BRISBANE - AUSTRALIA"),
                 ("2026-01-01 08:10:00", "Delivered - Signed for by: K LEE BRISBANE - AUSTRALIA"),
                 ("2025-12-31 04:00:00", "Arrived at DHL Delivery Facility BRISBANE - AUSTRALIA")],
         status="delivered", case_type="year_boundary"),

    # ---------- Cases based on real-world exception patterns (fictional numbers) ----------
    dict(num="0079350011112200001141", carrier="CTT Express", platform="运输途中 · 2天", route="西班牙->西班牙",
         events=[("2025-12-20 10:15:00", "Envío admitido MADRID"),
                 ("2025-12-21 16:40:00", "Envío anulado")],
         status="cancelled", case_type="cancelled_spanish"),
    dict(num="1ZR9X0000300000042", carrier="UPS", platform="可能异常 · 0天", route="美国->美国",
         events=[("2025-12-21 18:00:00", "Departed from Facility CHICAGO, IL, US"),
                 ("2025-12-22 09:45:23", "We've begun an investigation to locate the package.")],
         status="exception", case_type="investigation"),
    dict(num="490500000043", carrier="FedEx", platform="运输途中 · 3天", route="美国->美国",
         events=[("2025-12-20 22:10:00", "Arrived at FedEx hub MEMPHIS, TN, US"),
                 ("2025-12-21 02:30:00", "Shipment exception, Barcode label unreadable and replaced MEMPHIS, TN, US"),
                 ("2025-12-22 05:15:00", "Departed FedEx hub MEMPHIS, TN, US")],
         status="in_transit", case_type="recovered_history", history=True),
    dict(num="GFUS01000000000044", carrier="GOFO", platform="运输途中 · 3天", route="美国->美国",
         events=[("2025-12-20 09:00:00", "Pickup Exception, GOFO has not Received the Package from the Warehouse yet"),
                 ("2025-12-21 09:00:00", "Pickup Exception, GOFO has not Received the Package from the Warehouse yet"),
                 ("2025-12-21 17:20:00", "Pick up Success"),
                 ("2025-12-22 06:05:00", "Arrived at sorting center LOS ANGELES, CA")],
         status="in_transit", case_type="recovered_history", history=True),
    dict(num="UUS5XX0000000000045", carrier="UniUni", platform="查询不到", route="美国->美国",
         events=[],
         status="not_found", case_type="no_events"),
    dict(num="TBA000000000046", carrier="Amazon Shipping + Amazon MCF", carrier_true="Amazon Shipping",
         platform="· 0天", route="美国->美国",
         events=[],
         status="not_found", case_type="empty_status"),
    dict(num="9400111899223300112247", carrier="USPS", platform="运输途中 · 7天", route="美国->美国",
         events=[("2025-12-15 08:00:00", "Accepted at USPS Origin Facility RENO, NV 89501"),
                 ("2025-12-16 21:40:00", "In Transit to Next Facility")],
         status="in_transit", case_type="stuck"),
    dict(num="490500000048", carrier="FedEx", platform="成功签收 · 4天", route="美国->美国",
         events=[("2025-12-20 03:00:00", "Shipment exception, Barcode label unreadable and replaced NEWARK, NJ, US"),
                 ("2025-12-21 07:10:00", "On FedEx vehicle for delivery NEWARK, NJ, US"),
                 ("2025-12-21 14:30:00", "Delivered NEWARK, NJ, US")],
         status="delivered", case_type="recovered_history", history=True),
]

# The "today" used for the stuck-parcel rule when running on this sample data
AS_OF = datetime(2025, 12, 23, 0, 0, 0)

SEPARATORS = ["==========================================", "=====", "=============="]


def format_block(case, rng):
    lines = []
    if case.get("num") is not None:
        lines.append(f"单号：{case['num']}")
    if case.get("carrier") is not None:
        lines.append(f"物流商：{case['carrier']}")
    lines.append(f"包裹状态：{case['platform']}")
    lines.append(f"国家：{case['route']}")
    lines.extend(case.get("extra", []))

    # Default display: newest first, like the real export
    events = sorted(case["events"], key=lambda e: e[0], reverse=True)
    if case.get("shuffle"):
        rng.shuffle(events)
        # make sure the newest event is NOT on the first line
        if events and events[0] == max(events, key=lambda e: e[0]):
            events.append(events.pop(0))
    fmt = case.get("fmt", ISO)
    for ts, text in events:
        shown = datetime.strptime(ts, ISO).strftime(fmt)
        lines.append(f"{shown} {text}")
    return "\n".join(lines)


def main():
    rng = random.Random(42)  # fixed seed so the data is reproducible
    out_dir = Path("data")
    out_dir.mkdir(exist_ok=True)

    blocks, rows = [], []
    for i, case in enumerate(CASES, start=1):
        blocks.append(format_block(case, rng))
        latest = max((e[0] for e in case["events"]), default="")
        history = case.get("history", False)
        level, _ = alert_for(case["status"], latest, history, AS_OF)
        rows.append({
            "block_id": i,
            "tracking_number": case.get("num_true", case.get("num") or ""),
            "carrier": case.get("carrier_true", case.get("carrier") or ""),
            "latest_event_time": latest,
            "status": case["status"],
            "has_history_issue": "yes" if history else "no",
            "alert_level": level,
            "case_type": case["case_type"],
        })

    # Join blocks with separators of varying length to simulate messy exports
    text = ""
    for i, block in enumerate(blocks):
        text += block + "\n" + SEPARATORS[i % len(SEPARATORS)] + "\n\n"
    (out_dir / "sample_input.txt").write_text(text, encoding="utf-8")

    with open(out_dir / "labels.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(blocks)} blocks to data/sample_input.txt")
    print("Wrote answer key to data/labels.csv")


if __name__ == "__main__":
    main()
