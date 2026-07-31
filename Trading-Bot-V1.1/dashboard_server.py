"""Serve the dashboard and the bot's live state from one safe local web root."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from config import settings
from core.market_clock import ist_now
from core.storage import Storage


class DashboardHandler(SimpleHTTPRequestHandler):
    """Static dashboard plus read-only JSON endpoints backed by Storage."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(settings.reports_dir), **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route == "/api/positions":
            return self._send_json([position.to_dict() for position in Storage(settings.data_dir).load_positions()])
        if route == "/api/history":
            return self._send_json(Storage(settings.data_dir).load_history())
        if route == "/api/daily-summary":
            return self._send_json(self._daily_summary())
        if route == "/api/symbols":
            return self._send_json(settings.symbols)
        if route in {"/", "/dashboard.html"}:
            self.path = "/dashboard.html"
        return super().do_GET()

    def _send_json(self, payload: object) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _daily_summary() -> dict:
        storage = Storage(settings.data_dir)
        today = ist_now().date().isoformat()
        history = storage.load_history()
        today_history = [item for item in history if str(item.get("created_at", "")).startswith(today)]
        return {
            "date": today,
            "active_positions": len(storage.load_positions()),
            "buy_signals": sum(str(item.get("action", "")).upper() == "BUY" for item in today_history),
            "sell_signals": sum(str(item.get("action", "")).upper() == "SELL" for item in today_history),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the NSE trading dashboard")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"Dashboard available at http://{args.host}:{args.port}/dashboard.html")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
