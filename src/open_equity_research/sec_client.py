from __future__ import annotations

import gzip
import json
import threading
import time
import urllib.error
import urllib.request
import zlib
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings
from .exceptions import DataSourceError
from .io_utils import atomic_write_json, atomic_write_text, load_json, sha256_text
from .models import Filing


class RateLimiter:
    def __init__(self, interval_seconds: float) -> None:
        self.interval_seconds = interval_seconds
        self._lock = threading.Lock()
        self._last_request = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            sleep_for = self.interval_seconds - (now - self._last_request)
            if sleep_for > 0:
                time.sleep(sleep_for)
            self._last_request = time.monotonic()


class SECClient:
    """Small SEC EDGAR client with declared identity, caching, retries, and throttling."""

    TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
    DATA_BASE = "https://data.sec.gov"
    ARCHIVE_BASE = "https://www.sec.gov/Archives/edgar/data"

    def __init__(self, settings: Settings, *, force_refresh: bool = False) -> None:
        settings.validate_network_access()
        self.settings = settings
        self.force_refresh = force_refresh
        self.cache_dir = settings.workspace / ".cache" / "sec"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.rate_limiter = RateLimiter(settings.request_interval_seconds)

    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / f"{sha256_text(url)}.json"

    def _cache_is_fresh(self, path: Path) -> bool:
        if not path.exists() or self.force_refresh:
            return False
        age_seconds = time.time() - path.stat().st_mtime
        return age_seconds <= self.settings.cache_ttl_hours * 3600

    @staticmethod
    def _decode_response(raw: bytes, content_encoding: str | None) -> bytes:
        encoding = (content_encoding or "").lower()
        if "gzip" in encoding:
            return gzip.decompress(raw)
        if "deflate" in encoding:
            try:
                return zlib.decompress(raw)
            except zlib.error:
                return zlib.decompress(raw, -zlib.MAX_WBITS)
        return raw

    def _get_json(self, url: str) -> Any:
        cache_path = self._cache_path(url)
        if self._cache_is_fresh(cache_path):
            cached = load_json(cache_path)
            if cached is not None:
                return cached

        headers = {
            "User-Agent": self.settings.sec_user_agent,
            "Accept": "application/json, text/plain;q=0.9, */*;q=0.1",
            "Accept-Encoding": "gzip, deflate",
        }
        last_error: Exception | None = None
        for attempt in range(1, self.settings.max_retries + 1):
            self.rate_limiter.wait()
            request = urllib.request.Request(url, headers=headers, method="GET")
            try:
                with urllib.request.urlopen(
                    request, timeout=self.settings.request_timeout_seconds
                ) as response:
                    raw = response.read()
                    decoded = self._decode_response(raw, response.headers.get("Content-Encoding"))
                    payload = json.loads(decoded.decode("utf-8"))
                    atomic_write_json(cache_path, payload)
                    return payload
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code not in {403, 429, 500, 502, 503, 504}:
                    break
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                delay = float(retry_after) if retry_after and retry_after.isdigit() else min(2**attempt, 10)
                time.sleep(delay)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                last_error = exc
                time.sleep(min(2**attempt, 10))

        raise DataSourceError(f"Unable to fetch SEC data from {url}: {last_error}")

    def resolve_ticker(self, ticker: str) -> dict[str, str]:
        target = ticker.strip().upper()
        payload = self._get_json(self.TICKERS_URL)
        records: list[dict[str, Any]] = []
        if isinstance(payload, dict) and isinstance(payload.get("fields"), list):
            fields = payload["fields"]
            for row in payload.get("data", []):
                records.append(dict(zip(fields, row, strict=False)))
        elif isinstance(payload, dict):
            records = [value for value in payload.values() if isinstance(value, dict)]
        else:
            raise DataSourceError("Unexpected SEC ticker mapping format")

        for record in records:
            if str(record.get("ticker", "")).upper() == target:
                cik = str(record.get("cik", record.get("cik_str", ""))).zfill(10)
                return {
                    "ticker": target,
                    "cik": cik,
                    "name": str(record.get("name", record.get("title", ""))),
                    "exchange": str(record.get("exchange", "") or ""),
                }
        raise DataSourceError(f"Ticker {target!r} was not found in the SEC mapping")


    def get_document_text(self, url: str) -> str:
        """Fetch and cache a public filing document as text.

        HTML is returned unchanged so that callers can preserve a raw snapshot before parsing.
        """
        cache_path = self.cache_dir / f"{sha256_text(url)}.txt"
        if self._cache_is_fresh(cache_path):
            return cache_path.read_text(encoding="utf-8", errors="replace")

        headers = {
            "User-Agent": self.settings.sec_user_agent,
            "Accept": "text/html, text/plain;q=0.9, */*;q=0.1",
            "Accept-Encoding": "gzip, deflate",
        }
        last_error: Exception | None = None
        for attempt in range(1, self.settings.max_retries + 1):
            self.rate_limiter.wait()
            request = urllib.request.Request(url, headers=headers, method="GET")
            try:
                with urllib.request.urlopen(
                    request, timeout=self.settings.request_timeout_seconds
                ) as response:
                    raw = response.read()
                    decoded = self._decode_response(raw, response.headers.get("Content-Encoding"))
                    charset = response.headers.get_content_charset() or "utf-8"
                    text = decoded.decode(charset, errors="replace")
                    atomic_write_text(cache_path, text)
                    return text
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code not in {403, 429, 500, 502, 503, 504}:
                    break
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                delay = float(retry_after) if retry_after and retry_after.isdigit() else min(2**attempt, 10)
                time.sleep(delay)
            except (urllib.error.URLError, TimeoutError, UnicodeError) as exc:
                last_error = exc
                time.sleep(min(2**attempt, 10))
        raise DataSourceError(f"Unable to fetch SEC filing document from {url}: {last_error}")

    def get_submissions(self, cik: str) -> dict[str, Any]:
        return self._get_json(f"{self.DATA_BASE}/submissions/CIK{cik.zfill(10)}.json")

    def get_companyfacts(self, cik: str) -> dict[str, Any]:
        return self._get_json(f"{self.DATA_BASE}/api/xbrl/companyfacts/CIK{cik.zfill(10)}.json")

    @classmethod
    def filing_index_url(cls, cik: str, accession: str) -> str:
        cik_plain = str(int(cik))
        accession_plain = accession.replace("-", "")
        return f"{cls.ARCHIVE_BASE}/{cik_plain}/{accession_plain}/{accession}-index.html"

    @classmethod
    def filing_document_url(cls, cik: str, accession: str, primary_document: str) -> str:
        cik_plain = str(int(cik))
        accession_plain = accession.replace("-", "")
        return f"{cls.ARCHIVE_BASE}/{cik_plain}/{accession_plain}/{primary_document}"

    def recent_filings(
        self,
        submissions: dict[str, Any],
        cik: str,
        forms: set[str] | None = None,
        limit: int = 20,
    ) -> list[Filing]:
        recent = submissions.get("filings", {}).get("recent", {})
        if not isinstance(recent, dict):
            return []
        columns = {key: value for key, value in recent.items() if isinstance(value, list)}
        if not columns:
            return []
        length = max((len(values) for values in columns.values()), default=0)
        output: list[Filing] = []
        for index in range(length):
            def get(column: str) -> str:
                values = columns.get(column, [])
                return str(values[index]) if index < len(values) and values[index] is not None else ""

            form = get("form")
            if forms and form not in forms:
                continue
            accession = get("accessionNumber")
            primary_document = get("primaryDocument")
            source_url = (
                self.filing_document_url(cik, accession, primary_document)
                if accession and primary_document
                else self.filing_index_url(cik, accession)
            )
            output.append(
                Filing(
                    accession_number=accession,
                    form=form,
                    filing_date=get("filingDate"),
                    report_date=get("reportDate"),
                    primary_document=primary_document,
                    source_url=source_url,
                )
            )
            if len(output) >= limit:
                break
        return output

    @staticmethod
    def snapshot_metadata() -> dict[str, str]:
        return {
            "source": "SEC EDGAR",
            "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
