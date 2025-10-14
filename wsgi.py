"""Production WSGI entrypoint using Waitress.

Run with:
  - Windows PowerShell: .\.venv\Scripts\Activate.ps1; python wsgi.py
  - Or specify host/port: $env:HOST='0.0.0.0'; $env:PORT='8000'; python wsgi.py
"""

from __future__ import annotations

import os
import threading
import time
import webbrowser

try:
    from waitress import serve  # type: ignore
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "Waitress is not installed. Install it with: python -m pip install waitress"
    ) from exc

from src.webapp import app


def _open_browser_later(url: str, delay_seconds: float = 1.0) -> None:
    try:
        time.sleep(delay_seconds)
        webbrowser.open(url)
    except Exception:
        # Best-effort only; ignore failures silently in service/packaged contexts
        pass


def main() -> None:
    host = os.environ.get("HOST", "0.0.0.0")
    port_str = os.environ.get("PORT", "8000")
    try:
        port = int(port_str)
    except Exception:
        port = 8000
    # Open default browser shortly after server starts (local loopback URL)
    browser_url = os.environ.get("BROWSER_URL", f"http://127.0.0.1:{port}/")
    threading.Thread(target=_open_browser_later, args=(browser_url, 1.0), daemon=True).start()
    serve(app, listen=f"{host}:{port}")


if __name__ == "__main__":
    main()


