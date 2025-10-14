from __future__ import annotations

import argparse
from datetime import date as Date
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from .core import (
    CalculationInput,
    calculate,
    format_currency,
    format_date_for_slip,
)
from .persistence import append_history, load_clients, ensure_files_exist


APP_TITLE = "SRI VIJAYA DURGA COCONUT TRADERS"


def parse_positive_int(value: str, field_name: str) -> int:
    try:
        num = int(value)
    except Exception:
        raise argparse.ArgumentTypeError(f"{field_name} must be an integer")
    if num <= 0:
        raise argparse.ArgumentTypeError(f"{field_name} must be > 0")
    return num


def parse_positive_decimal(value: str, field_name: str) -> Decimal:
    try:
        d = Decimal(value)
    except (InvalidOperation, ValueError):
        raise argparse.ArgumentTypeError(f"{field_name} must be a number")
    if d <= 0:
        raise argparse.ArgumentTypeError(f"{field_name} must be > 0")
    return d


def parse_date(value: Optional[str]) -> Date:
    if not value:
        return Date.today()
    # Accept several common formats; store D-M-Y for slip and ISO for CSV
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise argparse.ArgumentTypeError(
        "Invalid date. Use YYYY-MM-DD or DD-MM-YYYY (or DD-MMM-YYYY)."
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Coconut billing CLI")
    p.add_argument("v_no", help="Voucher/Invoice No. (string)")
    p.add_argument("client_no", type=lambda s: parse_positive_int(s, "Client No."))
    p.add_argument("total_nuts", type=lambda s: parse_positive_int(s, "Total coconuts"))
    p.add_argument("price_each", type=lambda s: parse_positive_decimal(s, "Price each"))
    p.add_argument(
        "--date",
        dest="date_str",
        default=None,
        help="Date (YYYY-MM-DD or DD-MM-YYYY). Default: today",
    )
    p.add_argument(
        "--preview",
        action="store_true",
        help="Preview only (do not save history)",
    )
    p.add_argument(
        "--labor",
        type=lambda s: parse_positive_decimal(s, "Labor percent"),
        default=Decimal("11"),
        help="Labor percent of total nuts (default 11)",
    )
    return p


def render_slip(title: str, result) -> str:
    width = 40
    lines = []

    # Header centered
    header = title.center(width)
    lines.append(header)

    # Date slightly right under header
    date_str = format_date_for_slip(result.date)
    date_line = date_str.rjust(width - 1)
    lines.append(date_line)

    # V.No. and Client Name (not number)
    lines.append("".ljust(width))
    lines.append(f"V.No.: {result.invoice_no}")
    lines.append(f"Name: {result.client_name}")

    sep = "-" * width
    lines.append(sep)

    # Left labels with right aligned values
    label_width = 24
    value_width = width - label_width

    def row(label: str, value: str) -> None:
        lbl = label[: label_width - 1].ljust(label_width)
        val = value.rjust(value_width)
        lines.append(lbl + val)

    row("Total Coconuts:", str(result.total_nuts))
    row("Less (2.2%):", str(result.waste_nuts))
    row("Remaining Nuts:", str(result.remaining_nuts))
    row("Price Each:", f"₹{format_currency(result.price_each_rupees)}")

    lines.append(sep)

    row("Gross Amt:", f"₹{format_currency(result.gross_amount)}")
    row("Tax (1%):", f"₹{format_currency(result.tax_amount)}")
    row("Grader Chg:", f"₹{format_currency(result.labor_charges)}")

    lines.append(sep)

    row("Final Pay:", f"₹{format_currency(result.final_amount)}")

    lines.append(sep)

    # Signature block bottom-right
    # Leave one blank line for spacing
    lines.append("")
    sig = "Signature"
    name = "(S RamaPrasad)"
    lines.append(sig.rjust(width))
    lines.append(name.rjust(width))

    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    ensure_files_exist()
    parser = build_parser()
    args = parser.parse_args(argv)

    clients = load_clients()
    if args.client_no not in clients:
        parser.error("Client No. not found in clients.csv (must be 1-20)")

    slip_date = parse_date(args.date_str)

    input_data = CalculationInput(
        invoice_no=args.v_no,
        client_no=args.client_no,
        client_name=clients[args.client_no],
        total_nuts=args.total_nuts,
        price_each_rupees=args.price_each,
        date=slip_date,
        labor_percent=args.labor,
    )

    result = calculate(input_data)
    output = render_slip(APP_TITLE, result)
    print(output)

    if not args.preview:
        append_history(result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


