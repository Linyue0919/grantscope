"""Persistent grant workspace storage with a replaceable backend interface."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Protocol


class GrantStore(Protocol):
    def list_records(self, agency: str | None = None) -> list[dict]: ...
    def get(self, agency: str, opportunity_id: str) -> dict | None: ...
    def save(self, agency: str, opportunity_id: str, updates: dict) -> dict: ...
    def remove(self, agency: str, opportunity_id: str) -> bool: ...


def record_key(agency: str, opportunity_id: str) -> str:
    return f"{str(agency).strip()}::{str(opportunity_id).strip()}"


class LocalGrantStore:
    """Atomic local JSON store for development."""

    def __init__(self, path: str | os.PathLike | None = None):
        self.path = Path(path) if path else Path(os.environ.get("GRANTSCOPE_DATA_DIR", ".grantscope")) / "grants.json"

    def _read(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError("Grant workspace storage could not be read.") from exc
        if not isinstance(data, dict):
            raise RuntimeError("Grant workspace storage has an invalid format.")
        return {str(key): value for key, value in data.items() if isinstance(value, dict)}

    def _write(self, records: dict[str, dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=self.path.parent, prefix=".grants-", suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(records, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except OSError as exc:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise RuntimeError("Grant workspace storage could not be written.") from exc

    def list_records(self, agency: str | None = None) -> list[dict]:
        records = list(self._read().values())
        if agency is not None:
            records = [record for record in records if record.get("agency") == agency]
        return sorted(records, key=lambda record: (record.get("agency", ""), record.get("title", "")))

    def get(self, agency: str, opportunity_id: str) -> dict | None:
        return self._read().get(record_key(agency, opportunity_id))

    def save(self, agency: str, opportunity_id: str, updates: dict) -> dict:
        agency, opportunity_id = str(agency).strip(), str(opportunity_id).strip()
        if not agency or not opportunity_id:
            raise ValueError("Agency and opportunity ID are required.")
        records = self._read()
        key = record_key(agency, opportunity_id)
        current = records.get(key, {"agency": agency, "opportunity_id": opportunity_id})
        for field, value in updates.items():
            if field in {"bookmarked", "decision", "notes", "project_description", "viability_state", "research_depth",
                         "project_relevance", "strategic_relevance", "researched_at"}:
                current[field] = value
            elif field in {"title", "federal_agency", "close_date", "official_url"}:
                current.setdefault(field, value)
        current.setdefault("bookmarked", True)
        records[key] = current
        self._write(records)
        return current

    def remove(self, agency: str, opportunity_id: str) -> bool:
        records = self._read()
        key = record_key(agency, opportunity_id)
        if key not in records:
            return False
        del records[key]
        self._write(records)
        return True
