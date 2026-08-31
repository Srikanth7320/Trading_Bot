"""Serve the dashboard and the bot's live state from one safe local web root."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import urllib.request
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

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
        if route == "/api/scan-summary":
            return self._send_json(self._scan_summary())
        if route == "/api/daily-summary":
            return self._send_json(self._daily_summary())
        if route == "/api/symbols":
            return self._send_json(settings.symbols)
        if route == "/api/chart":
            return self._send_json(self._chart_data())
        if route == "/api/system-info":
            return self._send_json(self._system_info())
        if route in {"/", "/dashboard.html"}:
            self.path = "/dashboard.html"
        return super().do_GET()

    def _send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _chart_data(self) -> dict:
        query_params = parse_qs(urlparse(self.path).query)
        symbol = query_params.get("symbol", [""])[0].strip().upper()
        if not symbol:
            return {"error": "Missing symbol query parameter"}

        urls = [
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.NS?interval=1d&range=6mo",
            f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}.NS?interval=1d&range=6mo",
        ]
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
        }

        for url in urls:
            try:
                request = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(request, timeout=15) as response:
                    if response.status != 200:
                        continue
                    payload = json.loads(response.read().decode("utf-8"))
                    if payload.get("chart", {}).get("result"):
                        return payload
            except Exception as exc:
                continue

        return {"error": f"Unable to fetch chart data for {symbol} from Yahoo Finance"}

    @staticmethod
    def _scan_summary() -> dict:
        storage = Storage(settings.data_dir)
        metrics = storage.load_scan_metrics(20)
        if not metrics:
            return {
                "scan_count": 0,
                "average_buy_recommendations": 0,
                "average_qualified_signals": 0,
                "recent_scans": [],
            }

        average_buy_recommendations = sum(item.get("recommended", 0) for item in metrics) / len(metrics)
        average_qualified_signals = sum(item.get("qualified", 0) for item in metrics) / len(metrics)
        return {
            "scan_count": len(metrics),
            "average_buy_recommendations": round(average_buy_recommendations, 2),
            "average_qualified_signals": round(average_qualified_signals, 2),
            "recent_scans": metrics,
        }

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

    @staticmethod
    def _get_memory_info() -> dict[str, float]:
        def parse_meminfo() -> dict[str, int]:
            result = {}
            try:
                with open("/proc/meminfo", "r", encoding="utf-8") as handle:
                    for line in handle:
                        key, value = line.split(":", 1)
                        result[key.strip()] = int(value.strip().split()[0])
            except OSError:
                pass
            return result

        meminfo = parse_meminfo()
        total_kb = meminfo.get("MemTotal")
        available_kb = meminfo.get("MemAvailable") or meminfo.get("MemFree")
        if total_kb and available_kb:
            total_gb = round(total_kb / 1024 / 1024, 2)
            available_gb = round(available_kb / 1024 / 1024, 2)
            used_pct = round((1 - available_kb / total_kb) * 100, 1)
            return {"total_gb": total_gb, "available_gb": available_gb, "used_percent": used_pct}

        try:
            page_size = os.sysconf("SC_PAGE_SIZE")
            phys_pages = os.sysconf("SC_PHYS_PAGES")
            avail_pages = os.sysconf("SC_AVPHYS_PAGES")
            total_gb = round(page_size * phys_pages / 1024**3, 2)
            available_gb = round(page_size * avail_pages / 1024**3, 2)
            used_pct = round((1 - avail_pages / phys_pages) * 100, 1)
            return {"total_gb": total_gb, "available_gb": available_gb, "used_percent": used_pct}
        except (ValueError, OSError):
            return {"total_gb": 0.0, "available_gb": 0.0, "used_percent": 0.0}

    @staticmethod
    def _system_info() -> dict:
        mem = DashboardHandler._get_memory_info()
        try:
            disk = shutil.disk_usage("/")
            total_disk_gb = round(disk.total / 1024**3, 2)
            free_disk_gb = round(disk.free / 1024**3, 2)
            used_disk_pct = round((disk.total - disk.free) / disk.total * 100, 1)
        except OSError:
            total_disk_gb = free_disk_gb = used_disk_pct = 0.0

        uname = platform.uname()
        return {
            "os": platform.platform(),
            "hostname": uname.node,
            "architecture": uname.machine,
            "processor": uname.processor or platform.processor() or "Unknown",
            "total_memory_gb": mem["total_gb"],
            "available_memory_gb": mem["available_gb"],
            "memory_used_percent": mem["used_percent"],
            "total_storage_gb": total_disk_gb,
            "free_storage_gb": free_disk_gb,
            "storage_used_percent": used_disk_pct,
            "note": "This is AI Tool developed by K.V.Srikanth",
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

