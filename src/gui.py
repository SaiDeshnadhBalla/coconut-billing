from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date as Date
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, Optional

from .core import CalculationInput, calculate, format_currency, format_date_for_slip
from .persistence import ensure_files_exist, load_clients, append_history, save_slip_text
from .cli import render_slip, APP_TITLE  # reuse slip layout


def parse_date(value: Optional[str]) -> Date:
    if not value:
        return Date.today()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("Invalid date. Use YYYY-MM-DD or DD-MM-YYYY (or DD-MMM-YYYY).")


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Sri Venkateswara Coconuts")
        self.resizable(False, False)

        ensure_files_exist()
        self.client_map: Dict[int, str] = load_clients()

        self._build_ui()

    def _build_ui(self) -> None:
        pad = {"padx": 8, "pady": 6}

        container = ttk.Frame(self)
        container.grid(row=0, column=0, sticky="nsew")

        # Left form
        form = ttk.Frame(container)
        form.grid(row=0, column=0, sticky="nw")

        # V.No.
        ttk.Label(form, text="V.No.").grid(row=0, column=0, sticky="w", **pad)
        self.vno_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.vno_var, width=20).grid(row=0, column=1, **pad)

        # Client selection (Combobox with "no - name")
        ttk.Label(form, text="Client").grid(row=1, column=0, sticky="w", **pad)
        self.client_var = tk.StringVar()
        items = [f"{no} - {name}" for no, name in sorted(self.client_map.items())]
        self.client_combo = ttk.Combobox(form, textvariable=self.client_var, values=items, width=28, state="readonly")
        if items:
            self.client_combo.current(0)
        self.client_combo.grid(row=1, column=1, **pad)

        # Total nuts
        ttk.Label(form, text="Total Coconuts").grid(row=2, column=0, sticky="w", **pad)
        self.total_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.total_var, width=20).grid(row=2, column=1, **pad)

        # Price each
        ttk.Label(form, text="Price Each (₹)").grid(row=3, column=0, sticky="w", **pad)
        self.price_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.price_var, width=20).grid(row=3, column=1, **pad)

        # Date
        ttk.Label(form, text="Date (YYYY-MM-DD)").grid(row=4, column=0, sticky="w", **pad)
        self.date_var = tk.StringVar(value=Date.today().strftime("%Y-%m-%d"))
        ttk.Entry(form, textvariable=self.date_var, width=20).grid(row=4, column=1, **pad)

        # Buttons
        btns = ttk.Frame(form)
        btns.grid(row=5, column=0, columnspan=2, sticky="w", **pad)
        self.action_btn = ttk.Button(btns, text="Calculate", command=self.on_action)
        self.action_btn.grid(row=0, column=0, sticky="ew", **pad)
        self.save_btn = ttk.Button(btns, text="Save Slip", command=self.on_save)
        self.save_btn.grid(row=0, column=1, sticky="ew", **pad)

        # Right slip preview
        preview = ttk.Frame(container)
        preview.grid(row=0, column=1, sticky="nsew")
        ttk.Label(preview, text="Preview").grid(row=0, column=0, sticky="w", **pad)
        self.text = tk.Text(preview, width=48, height=26, font=("Courier New", 10))
        self.text.grid(row=1, column=0, **pad)

    def _gather_inputs(self) -> CalculationInput:
        vno = self.vno_var.get().strip()
        if not vno:
            raise ValueError("V.No. cannot be empty")

        client_display = self.client_var.get()
        try:
            client_no = int(client_display.split("-", 1)[0].strip())
        except Exception:
            raise ValueError("Please select a valid client")
        if client_no not in self.client_map:
            raise ValueError("Selected client not found")
        client_name = self.client_map[client_no]

        try:
            total = int(self.total_var.get())
        except Exception:
            raise ValueError("Total Coconuts must be a positive integer")
        if total <= 0:
            raise ValueError("Total Coconuts must be > 0")

        try:
            price = Decimal(self.price_var.get())
        except (InvalidOperation, ValueError):
            raise ValueError("Price Each must be a positive number")
        if price <= 0:
            raise ValueError("Price Each must be > 0")

        slip_date = parse_date(self.date_var.get().strip())

        return CalculationInput(
            invoice_no=vno,
            client_no=client_no,
            client_name=client_name,
            total_nuts=total,
            price_each_rupees=price,
            date=slip_date,
        )

    def _render(self, input_data: CalculationInput) -> str:
        result = calculate(input_data)
        return render_slip(APP_TITLE, result)

    def on_action(self) -> None:
        try:
            data = self._gather_inputs()
            result = calculate(data)
            slip = render_slip(APP_TITLE, result)
            # Do not auto-save; only append history
            append_history(result)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return
        # Update preview and inform
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", slip)
        messagebox.showinfo("Success", "Slip calculated. Use Save Slip to save if needed.")

    def on_save(self) -> None:
        try:
            data = self._gather_inputs()
            result = calculate(data)
            slip = render_slip(APP_TITLE, result)
            path = save_slip_text(result, slip)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return
        messagebox.showinfo("Saved", f"Slip saved to\n{path}")

    def on_clear(self) -> None:
        self.vno_var.set("")
        if self.client_combo["values"]:
            self.client_combo.current(0)
        self.total_var.set("")
        self.price_var.set("")
        self.date_var.set(Date.today().strftime("%Y-%m-%d"))
        self.text.delete("1.0", tk.END)


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()


