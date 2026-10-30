"""Telemetria centralizzata dei parametri di campionamento LLM (temperature, top_p).

Estrae esclusivamente parametri dichiarati dal servizio LLM (server-reported)
da eventi SSE o log diagnostici strutturati, validando tipi e intervalli
ed evitando falsi positivi da prompt, output testuali o messaggi di errore.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
from pathlib import Path
from typing import Any


HTTP_PROVIDER_CONFIG_ARGS = (
    "-c", 'model_provider="chatgpt-http"',
    "-c", 'model_providers.chatgpt-http.name="ChatGPT HTTP"',
    "-c", 'model_providers.chatgpt-http.base_url="https://chatgpt.com/backend-api/codex"',
    "-c", 'model_providers.chatgpt-http.wire_api="responses"',
    "-c", "model_providers.chatgpt-http.requires_openai_auth=true",
    "-c", "model_providers.chatgpt-http.supports_websockets=false",
)

HTTP_TRACE_RUST_LOG = "codex_api::sse::responses=trace"


@dataclass(frozen=True)
class SamplingTelemetry:
    temperature: float | None
    top_p: float | None
    source: str                 # "server_response" | "none" | "unsupported"
    status: str                 # "observed" | "not_reported" | "explicit_null" | "inconsistent" | "unavailable" | "unsupported_backend"
    transport: str | None       # "http" | "websocket" | None
    collection_mode: str        # "passive" | "http_trace"
    temperature_status: str | None = None
    top_p_status: str | None = None
    response_count: int = 0
    distinct_temperatures: tuple[float, ...] = ()
    distinct_top_p: tuple[float, ...] = ()
    client_requested_temperature: float | None = None
    client_requested_top_p: float | None = None
    details: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "source": self.source,
            "status": self.status,
            "transport": self.transport,
            "collection_mode": self.collection_mode,
            "temperature_status": self.temperature_status,
            "top_p_status": self.top_p_status,
            "response_count": self.response_count,
            "distinct_temperatures": list(self.distinct_temperatures),
            "distinct_top_p": list(self.distinct_top_p),
            "client_requested_temperature": self.client_requested_temperature,
            "client_requested_top_p": self.client_requested_top_p,
            "details": self.details,
        }

    def to_metrics_dict(self) -> dict[str, Any]:
        """Versione compatta per evaluation/metrics.json."""
        return self.to_dict()


def _validate_numeric(val: Any) -> float | None:
    """Valida un valore numerico escludendo booleani, NaN e infiniti."""
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        try:
            if math.isfinite(val):
                return float(val)
        except OverflowError:
            pass
    return None


def _is_response_payload(obj: Any) -> tuple[bool, dict[str, Any], str | None]:
    """Recognize only complete response objects inside a trusted response stream."""
    if not isinstance(obj, dict):
        return False, {}, None
    if obj.get("type") in ("response.created", "response.completed", "response.done", "response.incomplete", "response.failed"):
        response = obj.get("response")
    elif obj.get("object") in ("response", "chat.completion"):
        response = obj
    else:
        return False, {}, None
    if not isinstance(response, dict):
        return False, {}, None
    response_id = response.get("id")
    return True, response, response_id if isinstance(response_id, str) and response_id else None


# Accept only the known Codex SSE trace target, not agent output, JSONL or bare data:.
_TRACE_LINE = re.compile(
    r"^(?:\S+\s+)?TRACE\s+codex_api::sse::responses:\s*"
    r"(?:SSE event:|data:)\s*(.*)$"
)


class SamplingCollector:
    """Streaming, metadata-only extraction. Never retains raw SSE bodies or messages."""

    def __init__(self, collection_mode: str = "http_trace", backend: str = "docker_sandbox"):
        self.collection_mode = collection_mode
        self.backend = backend
        self.responses: dict[str, dict[str, dict[str, Any]]] = {}
        self.anonymous = 0
        self.overflow = False
        self.events_seen = 0

    def consume(self, line: str) -> bool:
        """Consume a *trusted Codex stderr* line. Return True for trace lines."""
        match = _TRACE_LINE.match(line.strip())
        if not match:
            return False
        # Cap individual lines to protect memory against enormous model messages.
        if len(line) > 2_000_000:
            self.overflow = True
            return True
        try:
            payload = json.loads(match.group(1))
        except (ValueError, TypeError):
            return True
        self.events_seen += 1
        accepted, response, response_id = _is_response_payload(payload)
        if not accepted:
            return True
        if not response_id:
            self.anonymous += 1
            response_id = f"__anonymous_{self.anonymous}"
        if response_id not in self.responses:
            if len(self.responses) >= 100_000:
                self.overflow = True
                return True
            self.responses[response_id] = {
                name: {"values": set(), "null": False, "invalid": False}
                for name in ("temperature", "top_p")
            }
        entry = self.responses[response_id]
        for name in ("temperature", "top_p"):
            if name not in response:
                continue
            raw = response[name]
            if raw is None:
                entry[name]["null"] = True
            else:
                number = _validate_numeric(raw)
                if number is None or number < 0 or (name == "top_p" and number > 1):
                    entry[name]["invalid"] = True
                else:
                    entry[name]["values"].add(number)
        return True

    def finish(self) -> SamplingTelemetry:
        if self.collection_mode == "disabled":
            return SamplingTelemetry(None, None, "none", "disabled", None, "disabled",
                                     temperature_status="disabled", top_p_status="disabled")
        if self.backend not in ("codex_cli", "docker_sandbox"):
            return SamplingTelemetry(None, None, "unsupported", "unsupported_backend",
                                     None, self.collection_mode, temperature_status="unsupported_backend",
                                     top_p_status="unsupported_backend")
        def summarize(name: str) -> tuple[float | None, str, tuple[float, ...]]:
            vals: set[float] = set()
            invalid = self.overflow
            null = False
            for response in self.responses.values():
                part = response[name]
                vals.update(part["values"])
                null |= part["null"]
                invalid |= part["invalid"]
            distinct = tuple(sorted(vals))
            if len(distinct) > 1:
                return None, "inconsistent", distinct
            if invalid:
                return None, "invalid", distinct
            if distinct:
                return distinct[0], "observed", distinct
            if null:
                return None, "explicit_null", distinct
            return None, "not_reported" if self.responses else "unavailable", distinct

        temperature, ts, temps = summarize("temperature")
        top_p, ps, top_ps = summarize("top_p")
        if "inconsistent" in (ts, ps):
            status = "inconsistent"
        elif "invalid" in (ts, ps):
            status = "invalid"
        elif ts == ps:
            status = ts
        else:
            status = "partial"
        found = bool(self.responses)
        return SamplingTelemetry(
            temperature, top_p, "server_response" if found else "none", status,
            "http" if found else None, self.collection_mode,
            temperature_status=ts, top_p_status=ps, response_count=len(self.responses),
            distinct_temperatures=temps, distinct_top_p=top_ps,
            details=("Valori discordanti tra risposte." if status == "inconsistent" else
                     "Limite di telemetria raggiunto." if self.overflow else None),
        )


def parse_sampling_telemetry(stderr_text: str = "", events_text: str = "",
                             collection_mode: str = "passive", backend: str = "codex_cli") -> SamplingTelemetry:
    """Parse trusted stderr only; JSONL, prompts, and arbitrary output are not evidence."""
    collector = SamplingCollector(collection_mode=collection_mode, backend=backend)
    if collection_mode == "disabled":
        return collector.finish()
    for line in stderr_text.splitlines():
        collector.consume(line)
    return collector.finish()


def merge_sampling_telemetries(telemetries: list[SamplingTelemetry],
                               *, collection_mode: str = "http_trace") -> SamplingTelemetry:
    """Combine isolated phase observations, preserving discordance and missing fields."""
    if collection_mode == "disabled":
        return SamplingCollector("disabled").finish()
    if not telemetries:
        return SamplingCollector(collection_mode).finish()

    def combine(name: str) -> tuple[float | None, str, tuple[float, ...]]:
        values: set[float] = set()
        statuses = []
        for t in telemetries:
            statuses.append(getattr(t, name + "_status") or t.status)
            values.update(getattr(t, "distinct_" + ("temperatures" if name == "temperature" else "top_p")))
            value = getattr(t, name)
            if value is not None:
                values.add(value)
        distinct = tuple(sorted(values))
        if len(distinct) > 1 or "inconsistent" in statuses:
            return None, "inconsistent", distinct
        if "invalid" in statuses:
            return None, "invalid", distinct
        if distinct:
            return distinct[0], "observed", distinct
        for status in ("explicit_null", "not_reported", "unavailable", "unsupported_backend", "disabled"):
            if status in statuses:
                return None, status, distinct
        return None, "unavailable", distinct

    t, ts, temps = combine("temperature")
    p, ps, top_ps = combine("top_p")
    if "inconsistent" in (ts, ps):
        status = "inconsistent"
    elif "invalid" in (ts, ps):
        status = "invalid"
    elif ts == ps:
        status = ts
    else:
        status = "partial"
    observed = any(x.source == "server_response" for x in telemetries)
    return SamplingTelemetry(
        t, p, "server_response" if observed else "none", status,
        "http" if observed else None, collection_mode,
        temperature_status=ts, top_p_status=ps,
        response_count=sum(x.response_count for x in telemetries),
        distinct_temperatures=temps, distinct_top_p=top_ps,
        details="Valori discordanti tra fasi." if status == "inconsistent" else None,
    )


def run_http_trace_command(
    args: list[str] | tuple[str, ...], *, input_bytes: bytes, timeout: int,
    env: dict[str, str], backend: str, cwd: Path | None = None,
) -> tuple[bytes, bytes, int, bool, SamplingTelemetry]:
    """Run Codex while discarding raw SSE immediately; retain only numeric metadata.

    Two concurrent readers drain both pipes to avoid deadlock. No raw HTTP trace
    is written to disk or accumulated across the run. A fixed, non-sensitive
    diagnostic replaces stderr in this mode.
    """
    import subprocess
    import threading

    collector = SamplingCollector(collection_mode="http_trace", backend=backend)
    stdout_chunks: list[bytes] = []
    process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, env=env, cwd=cwd)
    assert process.stdin is not None and process.stdout is not None and process.stderr is not None

    def read_stdout() -> None:
        while True:
            chunk = process.stdout.read(65536)
            if not chunk:
                break
            stdout_chunks.append(chunk)

    def read_stderr() -> None:
        # The trace can contain user messages. Never save or append raw stderr.
        for raw_line in process.stderr:
            collector.consume(raw_line.decode("utf-8", errors="replace"))

    def send_stdin() -> None:
        try:
            process.stdin.write(input_bytes)
            process.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            process.stdin.close()

    threads = [
        threading.Thread(target=read_stdout, daemon=True),
        threading.Thread(target=read_stderr, daemon=True),
        threading.Thread(target=send_stdin, daemon=True),
    ]
    for worker in threads:
        worker.start()
    timed_out = False
    try:
        code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        code = 124
        process.wait()
    for worker in threads:
        worker.join(timeout=15)
    # Do not fabricate server-reported values if no complete trace was observed.
    telemetry = collector.finish()
    diagnostic = (b"Codex HTTP/SSE execution timed out.\n" if timed_out else
                  b"Codex HTTP/SSE execution failed; raw trace intentionally redacted.\n"
                  if code else b"")
    return b"".join(stdout_chunks), diagnostic, code, timed_out, telemetry


def extract_sampling_telemetry(
    logs_dir: Path,
    collection_mode: str = "passive",
    backend: str = "codex_cli",
) -> SamplingTelemetry:
    """Read traditional passive stderr; traced runs persist sanitized metadata directly."""
    if collection_mode == "disabled":
        return parse_sampling_telemetry(collection_mode=collection_mode, backend=backend)
    existing = load_sampling_telemetry(logs_dir) if collection_mode == "http_trace" else None
    if existing is not None:
        return existing
    stderr_file = logs_dir / "stderr.log"
    stderr_text = stderr_file.read_text(encoding="utf-8", errors="replace") if stderr_file.is_file() else ""
    return parse_sampling_telemetry(
        stderr_text=stderr_text, collection_mode=collection_mode, backend=backend,
    )


def save_sampling_telemetry(logs_dir: Path, telemetry: SamplingTelemetry) -> Path:
    """Persiste l'artefatto logs/aut/sampling_telemetry.json in modo sicuro."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    target = logs_dir / "sampling_telemetry.json"
    temp_file = target.with_suffix(".json.tmp")
    data = json.dumps(telemetry.to_dict(), indent=2, ensure_ascii=False) + "\n"
    temp_file.write_text(data, encoding="utf-8")
    temp_file.replace(target)
    return target


def load_sampling_telemetry(logs_dir: Path) -> SamplingTelemetry | None:
    """Carica sampling_telemetry.json se presente e valido."""
    target = logs_dir / "sampling_telemetry.json"
    if not target.is_file():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return SamplingTelemetry(
            temperature=_validate_numeric(data.get("temperature")),
            top_p=_validate_numeric(data.get("top_p")),
            source=str(data.get("source") or "none"),
            status=str(data.get("status") or "unavailable"),
            transport=data.get("transport"),
            collection_mode=str(data.get("collection_mode") or "passive"),
            temperature_status=data.get("temperature_status"),
            top_p_status=data.get("top_p_status"),
            response_count=int(data.get("response_count") or 0),
            distinct_temperatures=tuple(data.get("distinct_temperatures") or ()),
            distinct_top_p=tuple(data.get("distinct_top_p") or ()),
            client_requested_temperature=_validate_numeric(data.get("client_requested_temperature")),
            client_requested_top_p=_validate_numeric(data.get("client_requested_top_p")),
            details=data.get("details"),
        )
    except Exception:
        return None
