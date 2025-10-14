from __future__ import annotations

from datetime import date as Date
from decimal import Decimal

from src.core import CalculationInput, calculate


def test_sample_case():
    # Example: 5670 nuts @ 22 → waste 125 → remaining 5545 → gross 121,990
    # tax 1,219.90 → labor 623.70 → final 120,146.40.
    input_data = CalculationInput(
        invoice_no="001",
        client_no=1,
        client_name="Client 01",
        total_nuts=5670,
        price_each_rupees=Decimal("22"),
        date=Date(2025, 8, 10),
        labor_percent=Decimal("11"),
    )

    result = calculate(input_data)

    assert result.waste_nuts == 125
    assert result.remaining_nuts == 5545
    assert f"{result.gross_amount:.2f}" == "121990.00"
    assert f"{result.tax_amount:.2f}" == "1219.90"
    assert f"{result.labor_charges:.2f}" == "623.70"
    assert f"{result.final_amount:.2f}" == "120146.40"


def test_invalid_inputs():
    # total_nuts must be > 0
    try:
        calculate(
            CalculationInput(
                invoice_no="A",
                client_no=1,
                client_name="X",
                total_nuts=0,
                price_each_rupees=Decimal("10"),
                date=Date.today(),
            )
        )
    except ValueError:
        pass
    else:
        assert False, "Expected ValueError for total_nuts=0"

    # price_each must be > 0
    try:
        calculate(
            CalculationInput(
                invoice_no="A",
                client_no=1,
                client_name="X",
                total_nuts=1,
                price_each_rupees=Decimal("0"),
                date=Date.today(),
            )
        )
    except ValueError:
        pass
    else:
        assert False, "Expected ValueError for price_each=0"


