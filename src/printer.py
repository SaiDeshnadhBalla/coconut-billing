"""Printer stubs for future thermal/PDF output.

This module will integrate with python-escpos or generate PDFs.
For now, it only exposes a stub to keep imports consistent later.
"""

from __future__ import annotations

from .core import CalculationResult


def print_to_console(formatted_slip: str) -> None:
    print(formatted_slip)


def print_to_thermal(_result: CalculationResult) -> None:  # pragma: no cover - future work
    raise NotImplementedError("Thermal printing not implemented yet")


def export_pdf(_result: CalculationResult, _path: str) -> None:  # pragma: no cover - future work
    raise NotImplementedError("PDF export not implemented yet")


