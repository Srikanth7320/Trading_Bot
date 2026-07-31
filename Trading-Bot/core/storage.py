import csv
import json
from pathlib import Path
from typing import Any

from core.models import Position, Recommendation, SellDecision


class Storage:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.active_positions_file = self.data_dir / "active_positions.json"
        self.history_file = self.data_dir / "history.json"
        self.cooldown_file = self.data_dir / "cooldown.json"
        self.hourly_tracking_file = self.data_dir / "hourly_tracking.csv"
        self.signal_history_file = self.data_dir / "signal_history.csv"

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default

    def _write_json(self, path: Path, payload: Any) -> None:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load_positions(self) -> list[Position]:
        payload = self._read_json(self.active_positions_file, [])
        return [Position.from_dict(item) for item in payload]

    def save_positions(self, positions: list[Position]) -> None:
        self._write_json(self.active_positions_file, [position.to_dict() for position in positions])

    def append_signal(self, signal: Recommendation | SellDecision) -> None:
        row = signal.to_dict()
        self._append_csv(self.signal_history_file, row)
        history = self._read_json(self.history_file, [])
        history.append(row)
        self._write_json(self.history_file, history[-1000:])

    def append_tracking(self, row: dict[str, Any]) -> None:
        self._append_csv(self.hourly_tracking_file, row)

    def load_cooldown(self) -> dict[str, Any]:
        return self._read_json(self.cooldown_file, {})

    def save_cooldown(self, payload: dict[str, Any]) -> None:
        self._write_json(self.cooldown_file, payload)

    def load_history(self) -> list[dict[str, Any]]:
        return self._read_json(self.history_file, [])

    def _append_csv(self, path: Path, row: dict[str, Any]) -> None:
        write_header = not path.exists()
        with path.open("a", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=list(row.keys()), extrasaction="ignore")
            if write_header:
                writer.writeheader()
            writer.writerow(row)
