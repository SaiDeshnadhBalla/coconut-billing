from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from decimal import Decimal, ROUND_HALF_EVEN, getcontext
from typing import Optional


# Configure a sane decimal precision for monetary calculations
getcontext().prec = 28


@dataclass(frozen=True)
class CalculationInput:
    invoice_no: str
    client_no: int
    client_name: str
    total_nuts: int
    price_each_rupees: Decimal
    date: Date
    labor_percent: Decimal = Decimal("11")


@dataclass(frozen=True)
class CalculationResult:
    # Identifiers
    invoice_no: str
    client_no: int
    client_name: str
    date: Date

    # Inputs
    total_nuts: int
    price_each_rupees: Decimal
    labor_percent: Decimal

    # Derived quantities (nuts)
    waste_nuts: int
    remaining_nuts: int

    # Monetary values (rupees)
    gross_amount: Decimal
    tax_amount: Decimal
    labor_charges: Decimal
    final_amount: Decimal


def _round_waste_to_nearest_integer_half_even(nuts: int) -> int:
    """Compute 2.2% waste and round to nearest integer using banker's rounding.

    The spec requests waste_raw = total * 0.022 then round() (Python default is
    banker's rounding). We implement using Decimal with HALF_EVEN to match.
    """
    waste_raw = (Decimal(nuts) * Decimal("0.022"))
    # Quantize to integer with HALF_EVEN
    waste_quantized = waste_raw.quantize(Decimal("1"), rounding=ROUND_HALF_EVEN)
    return int(waste_quantized)


def _quantize_money(value: Decimal) -> Decimal:
    """Quantize to two decimal places using HALF_EVEN."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


def calculate(input_data: CalculationInput) -> CalculationResult:
    """Calculate all billing figures according to the business rules.

    Steps:
    - Waste = 2.2% of total nuts, rounded to nearest integer (banker's rounding)
    - Remaining = total - waste
    - Gross = remaining * price_each
    - Tax = 1% of gross
    - Labor = total_nuts * (labor_percent/100) [in rupees]
    - Final = Gross - Tax - Labor
    """
    if input_data.total_nuts <= 0:
        raise ValueError("Total coconuts must be a positive integer")

    if input_data.price_each_rupees <= Decimal("0"):
        raise ValueError("Price per coconut must be a positive number")

    if not input_data.invoice_no:
        raise ValueError("V.No. (invoice number) must be a non-empty string")

    # Allow 0 for ad-hoc/manual names that are not in the predefined list
    if input_data.client_no < 0:
        raise ValueError("Client number must be >= 0")

    # Nuts math
    waste_nuts = _round_waste_to_nearest_integer_half_even(input_data.total_nuts)
    remaining_nuts = input_data.total_nuts - waste_nuts

    # Monetary math
    gross_amount = Decimal(remaining_nuts) * input_data.price_each_rupees
    tax_amount = gross_amount * Decimal("0.01")
    labor_charges = Decimal(input_data.total_nuts) * (input_data.labor_percent / Decimal("100"))

    # Final
    final_amount = gross_amount - tax_amount - labor_charges

    # Quantize monetary outputs to 2 decimals for storage/presentation
    gross_amount = _quantize_money(gross_amount)
    tax_amount = _quantize_money(tax_amount)
    labor_charges = _quantize_money(labor_charges)
    final_amount = _quantize_money(final_amount)

    return CalculationResult(
        invoice_no=input_data.invoice_no,
        client_no=input_data.client_no,
        client_name=input_data.client_name,
        date=input_data.date,
        total_nuts=input_data.total_nuts,
        price_each_rupees=_quantize_money(input_data.price_each_rupees),
        labor_percent=input_data.labor_percent,
        waste_nuts=waste_nuts,
        remaining_nuts=remaining_nuts,
        gross_amount=gross_amount,
        tax_amount=tax_amount,
        labor_charges=labor_charges,
        final_amount=final_amount,
    )


def format_currency(value: Decimal) -> str:
    """Format currency with western thousands separators and 2 decimals."""
    return f"{value:,.2f}"


def format_date_for_slip(date_value: Date) -> str:
    """Format date as DD-MMM-YYYY for the printed slip."""
    return date_value.strftime("%d-%b-%Y")


def format_date_for_csv(date_value: Date) -> str:
    """Format date as ISO YYYY-MM-DD for CSV."""
    return date_value.strftime("%Y-%m-%d")


