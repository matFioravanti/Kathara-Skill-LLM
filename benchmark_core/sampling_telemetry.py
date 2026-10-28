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


def parse_sampling_telemetry(stderr_text: str = "", events_text: str = "",
                             collection_mode: str = "passive", backend: str = "codex_cli") -> SamplingTelemetry:
    """Parse response SSE from Codex's response trace, never generic CLI output.

    The log channel is the provenance boundary: arbitrary JSON, agent output and
    unlabelled `data:` lines cannot establish that a server sent a response.
    """
    if collection_mode == "disabled":
        return SamplingTelemetry(None, None, "none", "disabled", None, collection_mode,
                                 temperature_status="disabled", top_p_status="disabled")
    if backend not in ("codex_cli", "docker_sandbox") or (backend == "docker_sandbox" and collection_mode == "http_trace"):
        return SamplingTelemetry(None, None, "unsupported", "unsupported_backend", None, collection_mode,
                                 temperature_status="unsupported_backend", top_p_status="unsupported_backend",
                                 details=f"Sampling collection unavailable for {backend} in {collection_mode} mode.")
    responses: dict[str, dict[str, list[Any]]] = {}
    anonymous = 0
    for line in stderr_text.splitlines():
        # Only the known Codex response trace supplies provenance. JSONL events,
        # shell output and bare SSE text may contain arbitrary user-controlled text.
        match = re.match(r"^(?:\S+\s+)?TRACE\s+codex_api::sse::responses:\s*data:\s*(.*)$", line.strip())
        if not match:
            continue
        data = match.group(1)
        try:
            payload = json.loads(data.strip())
        except (ValueError, TypeError):
            continue
        accepted, response, response_id = _is_response_payload(payload)
        if not accepted:
            continue
        if response_id is None:
            anonymous += 1
            response_id = f"__anonymous_{anonymous}"
        entry = responses.setdefault(response_id, {"temperature": [], "top_p": []})
        for name in entry:
            if name in response:
                entry[name].append(response[name])

    def summarize(name: str) -> tuple[float | None, str, tuple[float, ...]]:
        values: set[float] = set()
        invalid = null = False
        for entry in responses.values():
            for raw in entry[name]:
                if raw is None:
                    null = True
                    continue
                number = _validate_numeric(raw)
                # General constraints only: provider-specific temperature ceilings
                # differ, and no provider-specific limit is inferred here.
                if number is None or number < 0 or (name == "top_p" and number > 1):
                    invalid = True
                else:
                    values.add(number)
        distinct = tuple(sorted(values))
        if len(distinct) > 1:
            return None, "inconsistent", distinct
        if invalid:
            return None, "invalid", distinct
        if distinct:
            return distinct[0], "observed", distinct
        if null:
            return None, "explicit_null", distinct
        return None, "not_reported" if responses else "unavailable", distinct

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
    return SamplingTelemetry(temperature, top_p, "server_response" if responses else "none", status,
                             "http" if responses else None, collection_mode,
                             temperature_status=ts, top_p_status=ps, response_count=len(responses),
                             distinct_temperatures=temps, distinct_top_p=top_ps,
                             details="Valori discordanti tra risposte." if status == "inconsistent" else None)


def extract_sampling_telemetry(
    logs_dir: Path,
    collection_mode: str = "passive",
    backend: str = "codex_cli",
) -> SamplingTelemetry:
    """Estrae la telemetria di campionamento leggendo i log in logs_dir."""
    if collection_mode == "disabled":
        return parse_sampling_telemetry(collection_mode=collection_mode, backend=backend)
    stderr_file = logs_dir / "stderr.log"
    stderr_text = stderr_file.read_text(encoding="utf-8", errors="replace") if stderr_file.is_file() else ""
    return parse_sampling_telemetry(
        stderr_text=stderr_text,
        collection_mode=collection_mode,
        backend=backend,
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
