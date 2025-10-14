from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import datetime, date as Date
import json
from decimal import Decimal
from pathlib import Path
from typing import Dict, Iterable, List, Tuple, Optional

from .core import CalculationResult, format_date_for_csv


DATA_DIR = Path(__file__).resolve().parent
CLIENTS_CSV = DATA_DIR / "clients.csv"
CLIENTS_JSON = DATA_DIR / "clients.json"
HISTORY_CSV = DATA_DIR / "history.csv"
SLIPS_DIR = DATA_DIR / "slips"
RANGE_DIR = DATA_DIR / "range_reports"
PARTIES_CSV = DATA_DIR / "parties.csv"


def ensure_files_exist() -> None:
    """Create CSV files with headers if they don't exist."""
    # Ensure slips directory
    SLIPS_DIR.mkdir(parents=True, exist_ok=True)
    # Ensure range reports directory
    RANGE_DIR.mkdir(parents=True, exist_ok=True)

    # Provide either JSON or CSV for clients. Prefer JSON if present.
    if not CLIENTS_JSON.exists() and not CLIENTS_CSV.exists():
        # Create a default JSON list of 20 placeholder clients
        default_clients = {str(i): f"Client {i:02d}" for i in range(1, 21)}
        CLIENTS_JSON.write_text(json.dumps(default_clients, indent=2), encoding="utf-8")

    if not CLIENTS_CSV.exists():
        CLIENTS_CSV.write_text("client_no,client_name\n", encoding="utf-8")

    # Ensure parties.csv exists (single column header)
    if not PARTIES_CSV.exists():
        PARTIES_CSV.write_text("party_name\n", encoding="utf-8")

    if not HISTORY_CSV.exists():
        headers = [
            "date",
            "v_no",
            "client_no",
            "client_name",
            "total_nuts",
            "waste",
            "remaining",
            "price_each",
            "gross",
            "tax",
            "labor",
            "final_amount",
            "created_at",
            "party_name",
        ]
        with HISTORY_CSV.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)


def load_clients() -> Dict[int, str]:
    """Load client number to name map from clients.csv."""
    ensure_files_exist()
    mapping: Dict[int, str] = {}
    if CLIENTS_JSON.exists():
        try:
            data = json.loads(CLIENTS_JSON.read_text(encoding="utf-8"))
            for k, v in data.items():
                try:
                    no = int(k)
                except Exception:
                    continue
                name = (v or "").strip()
                if no > 0 and name:
                    mapping[no] = name
        except Exception:
            # fall back to CSV
            pass

    if not mapping and CLIENTS_CSV.exists():
        with CLIENTS_CSV.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    no = int(row["client_no"])  # may raise
                except Exception:
                    continue
                name = (row.get("client_name") or "").strip()
                if no > 0 and name:
                    mapping[no] = name
    return mapping


def _ensure_history_has_party_column() -> None:
    if not HISTORY_CSV.exists():
        return
    with HISTORY_CSV.open("r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            header = []
        if "party_name" in header:
            return
        rows = list(reader)
    header.append("party_name")
    with HISTORY_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            row.append("")
            writer.writerow(row)


def append_history(result: CalculationResult, party_name: str = "") -> None:
    """Append a calculation result to history.csv with optional party_name."""
    ensure_files_exist()
    _ensure_history_has_party_column()

    fieldnames = [
        "date",
        "v_no",
        "client_no",
        "client_name",
        "total_nuts",
        "waste",
        "remaining",
        "price_each",
        "gross",
        "tax",
        "labor",
        "final_amount",
        "created_at",
        "party_name",
    ]

    row = {
        "date": format_date_for_csv(result.date),
        "v_no": result.invoice_no,
        "client_no": result.client_no,
        "client_name": result.client_name,
        "total_nuts": result.total_nuts,
        "waste": result.waste_nuts,
        "remaining": result.remaining_nuts,
        "price_each": f"{result.price_each_rupees:.2f}",
        "gross": f"{result.gross_amount:.2f}",
        "tax": f"{result.tax_amount:.2f}",
        "labor": f"{result.labor_charges:.2f}",
        "final_amount": f"{result.final_amount:.2f}",
        "created_at": datetime.utcnow().isoformat(timespec="seconds"),
        "party_name": party_name or "",
    }

    with HISTORY_CSV.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if f.tell() == 0:
            writer.writeheader()
        writer.writerow(row)


def load_parties() -> List[str]:
    """Load list of party names from parties.csv (unique, non-empty)."""
    ensure_files_exist()
    parties: List[str] = []
    if PARTIES_CSV.exists():
        with PARTIES_CSV.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = (row.get("party_name") or "").strip()
                if name:
                    parties.append(name)
    # de-duplicate while preserving order
    seen = set()
    unique: List[str] = []
    for p in parties:
        k = p.lower()
        if k in seen:
            continue
        seen.add(k)
        unique.append(p)
    return unique


def append_party_if_new(name: str) -> None:
    """Append a party name to parties.csv if it's not already present (case-insensitive)."""
    name = (name or "").strip()
    if not name:
        return
    ensure_files_exist()
    existing = set(p.lower() for p in load_parties())
    if name.lower() in existing:
        return
    with PARTIES_CSV.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["party_name"], extrasaction="ignore")
        if f.tell() == 0:
            writer.writeheader()
        writer.writerow({"party_name": name})


def _shorten_client_name(name: str) -> str:
    parts = [p for p in name.split() if p]
    if not parts:
        return "Client"
    if len(parts) == 1:
        return parts[0][:16]
    # First + Last
    return (parts[0] + parts[-1])[:24]


def slip_filename(result: CalculationResult) -> str:
    ymd = result.date.strftime("%Y%m%d")
    short = _shorten_client_name(result.client_name).replace(" ", "")
    return f"VNo{result.invoice_no}_{ymd}_{short}.txt"


def save_slip_text(result: CalculationResult, content: str) -> Path:
    ensure_files_exist()
    path = SLIPS_DIR / slip_filename(result)
    path.write_text(content, encoding="utf-8")
    return path


def save_slip_text_if_new(result: CalculationResult, content: str) -> Tuple[Path, bool]:
    """Save slip text only if a file does not already exist.

    Returns (path, was_created). If the file already existed, does not overwrite and
    returns (path, False).
    """
    ensure_files_exist()
    path = SLIPS_DIR / slip_filename(result)
    if path.exists():
        return path, False
    path.write_text(content, encoding="utf-8")
    return path, True


def _sanitize_filename_component(text: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in (text or "").strip())
    # collapse multiple underscores
    while "__" in safe:
        safe = safe.replace("__", "_")
    return safe.strip("._") or "NA"


def _range_report_path(party_name: str, from_vno: int, to_vno: int, on_date: Date) -> Path:
    party_slug = _sanitize_filename_component(party_name)
    date_tag = on_date.strftime("%Y%m%d")
    filename = f"{date_tag}_V{from_vno}-{to_vno}_{party_slug}.txt"
    return RANGE_DIR / filename


def save_range_report_if_new(
    party_name: str, from_vno: int, to_vno: int, report_text: str, on_date: Date
) -> tuple[Path, bool]:
    """Save voucher range text deterministically; don't overwrite if already exists.

    Returns (path, created).
    """
    ensure_files_exist()
    path = _range_report_path(party_name, from_vno, to_vno, on_date)
    if path.exists():
        return path, False
    header = (
        f"Party: {party_name}\n"
        f"Range: {from_vno}..{to_vno}\n"
        f"Saved At (UTC): {datetime.utcnow().isoformat(timespec='seconds')}\n\n"
    )
    path.write_text(header + (report_text or ""), encoding="utf-8")
    return path, True


# Backwards-compatible helper (unused now), keeps previous API
def save_range_report(party_name: str, from_vno: int, to_vno: int, report_text: str) -> Path:
    path, _ = save_range_report_if_new(party_name, from_vno, to_vno, report_text, Date.today())
    return path


def read_history_rows() -> List[Dict[str, str]]:
    ensure_files_exist()
    if not HISTORY_CSV.exists():
        return []
    with HISTORY_CSV.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def deduplicate_history() -> int:
    """Remove duplicate rows from history.csv.

    Duplicates are defined as rows having the same (client_name, v_no, final_amount)
    after trimming whitespace and normalizing case for the name. Keeps the first
    occurrence and discards subsequent ones. Returns the number of removed rows.
    """
    ensure_files_exist()
    if not HISTORY_CSV.exists():
        return 0
    with HISTORY_CSV.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        header = reader.fieldnames or []
    if not rows:
        return 0

    # Ensure party_name column exists in header
    if "party_name" not in header:
        header.append("party_name")
        for r in rows:
            r.setdefault("party_name", "")

    seen_keys = set()
    unique_rows: List[Dict[str, str]] = []
    removed = 0
    for r in rows:
        name = (r.get("client_name") or r.get("Name") or "").strip().lower()
        vno = str(r.get("v_no") or r.get("V.No.") or "").strip()
        amt = str(r.get("final_amount") or r.get("Amount") or "").strip()
        key = (name, vno, amt)
        if key in seen_keys:
            removed += 1
            continue
        seen_keys.add(key)
        unique_rows.append(r)

    with HISTORY_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        for r in unique_rows:
            writer.writerow(r)
    return removed

