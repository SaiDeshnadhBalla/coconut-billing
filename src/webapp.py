from __future__ import annotations

from datetime import date as Date, datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, Optional
import json
import time

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    send_from_directory,
)

from .core import CalculationInput, calculate
from .cli import render_slip, APP_TITLE
from .persistence import (
    ensure_files_exist,
    load_clients,
    append_history,
    save_slip_text,
    save_slip_text_if_new,
    SLIPS_DIR,
    read_history_rows,
    load_parties,
    deduplicate_history,
    save_range_report,
    save_range_report_if_new,
)
from pathlib import Path


app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-key-change-later"
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.jinja_env.auto_reload = True


@app.after_request
def _disable_html_cache(response):
    try:
        ct = (response.headers.get("Content-Type") or "").lower()
        if ct.startswith("text/html"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
    except Exception:
        pass
    return response


def parse_date(value: Optional[str]) -> Date:
    if not value:
        return Date.today()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("Invalid date. Use YYYY-MM-DD or DD-MM-YYYY (or DD-MMM-YYYY).")


def get_clients() -> Dict[int, str]:
    ensure_files_exist()
    return load_clients()


def _format_indian_number(n: int) -> str:
    """Format integer using Indian numbering system (e.g., 1545468 -> 15,45,468)."""
    s = str(abs(int(n)))
    if len(s) <= 3:
        out = s
    else:
        last3 = s[-3:]
        rest = s[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        out = ",".join(groups + [last3])
    return out


@app.route("/")
def index():
    clients = get_clients()
    static_dir = Path(__file__).resolve().parent / "static"
    logo_file = None
    if (static_dir / "logo.png").exists():
        logo_file = "logo.png"
    elif (static_dir / "logo.svg").exists():
        logo_file = "logo.svg"
    removed = deduplicate_history()  # Optional cleanup on landing
    return render_template(
        "index.html",
        title=APP_TITLE,
        clients=sorted(clients.items()),
        parties=load_parties(),
        today_iso=Date.today().strftime("%Y-%m-%d"),
        slip_text=None,
        message=None,
        error=None,
        saved_filename=None,
        has_logo=bool(logo_file),
        logo_url=(url_for("static", filename=logo_file) if logo_file else None),
        report_text=None,
    )


@app.route("/dashboard")
def dashboard():
    """Simple dashboard with two primary actions: Pay Slip and Voucher Range."""
    static_dir = Path(__file__).resolve().parent / "static"
    logo_file = None
    if (static_dir / "logo.png").exists():
        logo_file = "logo.png"
    elif (static_dir / "logo.svg").exists():
        logo_file = "logo.svg"
    return render_template(
        "dashboard.html",
        title=APP_TITLE,
        has_logo=bool(logo_file),
        logo_url=(url_for("static", filename=logo_file) if logo_file else None),
    )


@app.route("/generate", methods=["POST"])
def generate():
    clients = get_clients()

    def render_with(error: Optional[str] = None, slip_text: Optional[str] = None, filename: Optional[str] = None):
        static_dir = Path(__file__).resolve().parent / "static"
        logo_file = None
        if (static_dir / "logo.png").exists():
            logo_file = "logo.png"
        elif (static_dir / "logo.svg").exists():
            logo_file = "logo.svg"
        # After save, optionally de-duplicate silently
        removed = deduplicate_history()
        return render_template(
            "index.html",
            title=APP_TITLE,
            clients=sorted(clients.items()),
            parties=load_parties(),
            today_iso=Date.today().strftime("%Y-%m-%d"),
            slip_text=slip_text,
            error=error,
            message=(None if error else ("Slip saved" if filename else None)),
            saved_filename=filename,
            has_logo=bool(logo_file),
            logo_url=(url_for("static", filename=logo_file) if logo_file else None),
            report_text=None,
            form={
                "v_no": request.form.get("v_no", ""),
                "client_no": request.form.get("client_no", ""),
                "client_name": request.form.get("client_name", ""),
                "total_nuts": request.form.get("total_nuts", ""),
                "price_each": request.form.get("price_each", ""),
                "date": request.form.get("date", Date.today().strftime("%Y-%m-%d")),
                "party_name": request.form.get("party_name", ""),
            },
        )

    try:
        start_ts = time.perf_counter()
        v_no = (request.form.get("v_no") or "").strip()
        if not v_no:
            return render_with(error="V.No. cannot be empty")

        # Accept manual name entry; if matches known client, use its number, else number 0
        typed_name = (request.form.get("client_name") or "").strip()
        if typed_name:
            name_to_no = {v: k for k, v in clients.items()}
            client_no = name_to_no.get(typed_name, 0)
            client_name = typed_name
        else:
            try:
                client_no = int(request.form.get("client_no") or 0)
            except Exception:
                return render_with(error="Client No. must be an integer")
            if client_no not in clients:
                return render_with(error="Client No. not found in clients list (1–20)")
            client_name = clients[client_no]

        try:
            total_nuts = int(request.form.get("total_nuts") or 0)
        except Exception:
            return render_with(error="Total Coconuts must be a positive integer")
        if total_nuts <= 0:
            return render_with(error="Total Coconuts must be > 0")

        try:
            price_each = Decimal(request.form.get("price_each") or "0")
        except (InvalidOperation, ValueError):
            return render_with(error="Price Each must be a positive number")
        if price_each <= 0:
            return render_with(error="Price Each must be > 0")

        try:
            slip_date = parse_date(request.form.get("date"))
        except Exception as e:
            return render_with(error=str(e))

        input_data = CalculationInput(
            invoice_no=v_no,
            client_no=client_no,
            client_name=client_name,
            total_nuts=total_nuts,
            price_each_rupees=price_each,
            date=slip_date,
        )
        result = calculate(input_data)
        slip = render_slip(APP_TITLE, result)

        # Do not auto-save slip; user can print or download if needed
        path = None
        created = False
        # capture optional party_name (new)
        party_name = (request.form.get("party_name") or "").strip()
        append_history(result, party_name=party_name)

        # Ensure user perceives loading for UX consistency (minimum 0.5 second)
        elapsed = time.perf_counter() - start_ts
        remaining = 0.5 - elapsed
        if remaining > 0:
            time.sleep(remaining)
        return render_with(error=None, slip_text=slip, filename=None)
    except Exception as e:
        return render_with(error=str(e))


@app.route("/voucher-range", methods=["POST"])
def voucher_range():
    clients = get_clients()

    def render_with(error: Optional[str] = None, report_text: Optional[str] = None, saved_range: Optional[str] = None):
        static_dir = Path(__file__).resolve().parent / "static"
        logo_file = None
        if (static_dir / "logo.png").exists():
            logo_file = "logo.png"
        elif (static_dir / "logo.svg").exists():
            logo_file = "logo.svg"
        return render_template(
            "index.html",
            title=APP_TITLE,
            clients=sorted(clients.items()),
            parties=load_parties(),
            today_iso=Date.today().strftime("%Y-%m-%d"),
            slip_text=None,
            error=error,
            message=(None if error else ("Report saved" if saved_range else ("Report ready" if report_text else None))),
            saved_filename=None,
            has_logo=bool(logo_file),
            logo_url=(url_for("static", filename=logo_file) if logo_file else None),
            report_text=report_text,
            form={
                "v_no": request.form.get("v_no", ""),
                "client_no": request.form.get("client_no", ""),
                "client_name": request.form.get("client_name", ""),
                "party_name": request.form.get("party_name", ""),
                "total_nuts": request.form.get("total_nuts", ""),
                "price_each": request.form.get("price_each", ""),
                "date": request.form.get("date", Date.today().strftime("%Y-%m-%d")),
                "range_from": request.form.get("range_from", ""),
                "range_to": request.form.get("range_to", ""),
            },
        )

    try:
        from_no = request.form.get("range_from")
        to_no = request.form.get("range_to")
        if not from_no or not to_no:
            return render_with(error="Please enter both From and To voucher numbers")
        try:
            a = int(from_no)
            b = int(to_no)
        except Exception:
            return render_with(error="Voucher numbers must be integers")
        if a > b:
            a, b = b, a

        rows = read_history_rows()
        filtered = []
        for r in rows:
            v = r.get("v_no") or r.get("V.No.") or ""
            try:
                v_int = int(str(v).strip())
            except Exception:
                continue
            if a <= v_int <= b:
                filtered.append((v_int, r))
        filtered.sort(key=lambda t: t[0])

        if not filtered:
            return render_with(report_text="No vouchers found in this range")

        # Build aligned report: index. Name (V.No.)  =  amount (columns aligned)
        entries = []
        for vnum, r in filtered:
            name = (r.get("client_name") or r.get("Name") or "").strip()
            amount = r.get("final_amount") or r.get("Amount") or "0"
            try:
                amt = float(amount)
            except Exception:
                amt = 0.0
            rupees = int(amt)
            paise = int(round((amt - rupees) * 100))
            amt_text = f"{_format_indian_number(rupees)}"
            if paise:
                amt_text += f".{paise:02d}"
            label = f"{name} ({vnum})"
            entries.append((label, amt_text))

        if not entries:
            return render_with(report_text="No vouchers found in this range")

        name_width = max(len(lbl) for lbl, _ in entries)
        amt_width = max(len(amt) for _, amt in entries)
        idx_width = len(str(len(entries)))
        lines = []
        for i, (lbl, amt) in enumerate(entries, start=1):
            lines.append(f"{str(i).rjust(idx_width)}. {lbl.ljust(name_width)}  =  {amt.rjust(amt_width)}")

        # Optional: de-duplicate before showing report
        deduplicate_history()
        report_text = "\n".join(lines)
        # Do not auto-save here; saving is done only via Save Range button
        return render_with(report_text=report_text)
    except Exception as e:
        return render_with(error=str(e))


@app.route("/slips/<path:filename>")
def download_slip(filename: str):
    return send_from_directory(SLIPS_DIR, filename, as_attachment=True)


@app.route("/slip-save", methods=["POST"])
def slip_save():
    try:
        payload = request.get_json(silent=True) or {}
        v_no = (payload.get("v_no") or "").strip()
        if not v_no:
            return (json.dumps({"ok": False, "message": "V.No. is required"}), 400, {"Content-Type": "application/json"})

        # Accept manual name entry; if matches known client, use its number, else number 0
        clients = get_clients()
        typed_name = (payload.get("client_name") or "").strip()
        client_no = 0
        client_name = typed_name
        if not typed_name:
            try:
                client_no = int(str(payload.get("client_no") or "0").strip())
            except Exception:
                client_no = 0
            if client_no not in clients:
                return (json.dumps({"ok": False, "message": "Client No. not found in clients list (1–20)"}), 400, {"Content-Type": "application/json"})
            client_name = clients[client_no]

        try:
            total_nuts = int(str(payload.get("total_nuts") or "0").strip())
        except Exception:
            return (json.dumps({"ok": False, "message": "Total Coconuts must be a positive integer"}), 400, {"Content-Type": "application/json"})
        if total_nuts <= 0:
            return (json.dumps({"ok": False, "message": "Total Coconuts must be > 0"}), 400, {"Content-Type": "application/json"})

        try:
            price_each = Decimal(str(payload.get("price_each") or "0").strip())
        except (InvalidOperation, ValueError):
            return (json.dumps({"ok": False, "message": "Price Each must be a positive number"}), 400, {"Content-Type": "application/json"})
        if price_each <= 0:
            return (json.dumps({"ok": False, "message": "Price Each must be > 0"}), 400, {"Content-Type": "application/json"})

        date_str = (payload.get("date") or "").strip()
        on_date = parse_date(date_str) if date_str else Date.today()

        input_data = CalculationInput(
            invoice_no=v_no,
            client_no=client_no,
            client_name=client_name,
            total_nuts=total_nuts,
            price_each_rupees=price_each,
            date=on_date,
        )
        result = calculate(input_data)
        slip = render_slip(APP_TITLE, result)

        path, created = save_slip_text_if_new(result, slip)
        if created:
            return (json.dumps({"ok": True, "filename": path.name}), 200, {"Content-Type": "application/json"})
        else:
            return (json.dumps({"ok": False, "message": f"Already saved: {path.name}"}), 200, {"Content-Type": "application/json"})
    except Exception as e:
        return (json.dumps({"ok": False, "message": str(e)}), 400, {"Content-Type": "application/json"})


@app.route("/voucher-range-save", methods=["POST"])
def voucher_range_save():
    try:
        payload = request.get_json(silent=True) or {}
        party_name = (payload.get("party_name") or "").strip()
        from_vno = int(str(payload.get("from_vno") or "0").strip())
        to_vno = int(str(payload.get("to_vno") or "0").strip())
        report_text = payload.get("report_text") or ""
        date_str = (payload.get("date") or "").strip()
        on_date = parse_date(date_str) if date_str else Date.today()
        path, created = save_range_report_if_new(party_name, min(from_vno, to_vno), max(from_vno, to_vno), report_text, on_date)
        if created:
            return (json.dumps({"ok": True, "filename": path.name}), 200, {"Content-Type": "application/json"})
        else:
            return (json.dumps({"ok": False, "message": f"Already saved: {path.name}"}), 200, {"Content-Type": "application/json"})
    except Exception as e:
        return (json.dumps({"ok": False, "message": str(e)}), 400, {"Content-Type": "application/json"})


@app.route("/voucher_get", methods=["GET"])
def voucher_get():
    try:
        v_no_str = (request.args.get("v_no") or "").strip()
        if not v_no_str:
            return (json.dumps({"ok": False, "message": "v_no is required"}), 400, {"Content-Type": "application/json"})
        try:
            v_no_int = int(v_no_str)
        except Exception:
            return (json.dumps({"ok": False, "message": "v_no must be an integer"}), 400, {"Content-Type": "application/json"})

        rows = read_history_rows()
        found = None
        # Prefer the most recent match
        for r in reversed(rows):
            try:
                rv = int(str(r.get("v_no") or r.get("V.No.") or "").strip())
            except Exception:
                continue
            if rv == v_no_int:
                found = r
                break

        if not found:
            return (json.dumps({"ok": False, "message": "Voucher not found"}), 404, {"Content-Type": "application/json"})

        # Extract fields with fallbacks
        client_name = (found.get("client_name") or found.get("Name") or "").strip()
        try:
            client_no = int(str(found.get("client_no") or "0").strip() or 0)
        except Exception:
            client_no = 0
        try:
            total_nuts = int(str(found.get("total_nuts") or found.get("Total") or "0").strip() or 0)
        except Exception:
            total_nuts = 0
        price_each_str = str(found.get("price_each") or found.get("Price") or "0").strip()
        try:
            price_each = Decimal(price_each_str)
        except (InvalidOperation, ValueError):
            price_each = Decimal("0")
        try:
            on_date = parse_date(str(found.get("date") or found.get("Date") or "").strip())
        except Exception:
            on_date = Date.today()

        # Recompute and render slip text
        try:
            input_data = CalculationInput(
                invoice_no=str(v_no_int),
                client_no=client_no,
                client_name=client_name,
                total_nuts=total_nuts,
                price_each_rupees=price_each,
                date=on_date,
            )
            result = calculate(input_data)
            slip_text = render_slip(APP_TITLE, result)
        except Exception:
            slip_text = None

        payload = {
            "ok": True,
            "data": {
                "v_no": str(v_no_int),
                "client_no": client_no,
                "client_name": client_name,
                "total_nuts": total_nuts,
                "price_each": float(price_each) if price_each is not None else 0.0,
                "date": on_date.strftime("%Y-%m-%d"),
                "slip_text": slip_text,
            },
        }
        return (json.dumps(payload), 200, {"Content-Type": "application/json"})
    except Exception as e:
        return (json.dumps({"ok": False, "message": str(e)}), 400, {"Content-Type": "application/json"})


if __name__ == "__main__":
    # For local development
    app.run(host="127.0.0.1", port=5000, debug=True)


