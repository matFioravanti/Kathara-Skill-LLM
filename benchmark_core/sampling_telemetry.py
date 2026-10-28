"""Telemetria centralizzata dei parametri di campionamento LLM (temperature, top_p).

Estrae esclusivamente parametri dichiarati dal servizio LLM (server-reported)
da eventi SSE o log diagnostici strutturati, validando tipi e intervalli
ed evitando falsi positivi da prompt, output testuali o messaggi di errore.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
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
            "response_count": self.response_count,
            "distinct_temperatures": list(self.distinct_temperatures),
            "distinct_top_p": list(self.distinct_top_p),
            "client_requested_temperature": self.client_requested_temperature,
            "client_requested_top_p": self.client_requested_top_p,
            "details": self.details,
        }

    def to_metrics_dict(self) -> dict[str, Any]:
        """Versione compatta per evaluation/metrics.json."""
        return {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "source": self.source,
            "status": self.status,
            "transport": self.transport,
            "collection_mode": self.collection_mode,
        }


def _validate_numeric(val: Any) -> float | None:
    """Valida un valore numerico escludendo booleani, NaN e infiniti."""
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        if math.isfinite(val):
            return float(val)
    return None


def _is_response_payload(obj: dict[str, Any]) -> tuple[bool, dict[str, Any], str | None]:
    """Determina se un oggetto JSON rappresenta un oggetto di risposta del modello.

    Restituisce (is_response, response_obj, response_id).
    Rifiuta esplicitamente agent_message, comandi di shell, output di tool o strutture generiche.
    """
    if not isinstance(obj, dict):
        return False, {}, None

    # Rifiuta eventi agent/tool noti di Codex ed Inspect
    if obj.get("type") in ("agent_message", "command_execution", "file_change", "mcp_tool_call", "web_search"):
        return False, {}, None
    item = obj.get("item")
    if isinstance(item, dict) and item.get("type") in ("agent_message", "command_execution", "file_change"):
        return False, {}, None

    # Caso 1: Evento SSE di Responses API (es. response.created, response.done, response.completed)
    event_type = obj.get("type")
    if isinstance(event_type, str) and event_type.startswith("response."):
        resp = obj.get("response")
        if isinstance(resp, dict):
            resp_id = resp.get("id") or obj.get("id") or obj.get("response_id")
            return True, resp, str(resp_id) if resp_id else None

    # Caso 2: Oggetto con campo "response" innestato
    resp = obj.get("response")
    if isinstance(resp, dict) and ("temperature" in resp or "top_p" in resp or resp.get("object") == "response"):
        resp_id = resp.get("id") or obj.get("id")
        return True, resp, str(resp_id) if resp_id else None

    # Caso 3: Oggetto top-level con object="response" o "chat.completion" o "chat.completion.chunk"
    obj_type = obj.get("object")
    if isinstance(obj_type, str) and obj_type in ("response", "chat.completion", "chat.completion.chunk"):
        resp_id = obj.get("id")
        return True, obj, str(resp_id) if resp_id else None

    # Caso 4: Oggetto con id "resp_..." o "chatcmpl-..." e campi di risposta
    cand_id = obj.get("id")
    if isinstance(cand_id, str) and (cand_id.startswith("resp_") or cand_id.startswith("chatcmpl-")):
        if any(k in obj for k in ("temperature", "top_p", "model", "status", "output", "choices", "usage")):
            return True, obj, cand_id

    # Caso 5: Oggetto con temperature/top_p e modello, senza tracce di comandi o output
    if ("temperature" in obj or "top_p" in obj) and "model" in obj:
        if not any(k in obj for k in ("command", "aggregated_output", "exit_code", "text")):
            return True, obj, str(cand_id) if cand_id else None

    return False, {}, None


def parse_sampling_telemetry(
    stderr_text: str = "",
    events_text: str = "",
    collection_mode: str = "passive",
    backend: str = "codex_cli",
) -> SamplingTelemetry:
    """Estrae i parametri di campionamento dai log stdout/stderr con parsing strutturato."""
    # Gestione preventiva per backend non supportati in modalità http_trace
    if backend == "docker_sandbox" and collection_mode == "http_trace":
        return SamplingTelemetry(
            temperature=None,
            top_p=None,
            source="unsupported",
            status="unsupported_backend",
            transport=None,
            collection_mode=collection_mode,
            details="La modalità http_trace non è supportata su backend docker_sandbox per incompatibilità con il proxy OAuth.",
        )

    transport_detected: str | None = None
    if "codex_api::sse" in stderr_text or "data:" in stderr_text:
        transport_detected = "http"

    # responses: response_id -> { "temperature": (present, value, is_null), "top_p": (present, value, is_null) }
    responses: dict[str, dict[str, Any]] = {}
    anon_counter = 0

    def _process_candidate(payload: Any) -> None:
        nonlocal anon_counter, transport_detected
        if not isinstance(payload, dict):
            return
        is_resp, resp_obj, resp_id = _is_response_payload(payload)
        if not is_resp:
            return

        transport_detected = transport_detected or "http"
        if not resp_id:
            anon_counter += 1
            resp_id = f"anon_resp_{anon_counter}"

        has_temp = "temperature" in resp_obj
        raw_temp = resp_obj.get("temperature")
        valid_temp = _validate_numeric(raw_temp)
        temp_is_null = has_temp and (raw_temp is None)

        has_top_p = "top_p" in resp_obj
        raw_top_p = resp_obj.get("top_p")
        valid_top_p = _validate_numeric(raw_top_p)
        top_p_is_null = has_top_p and (raw_top_p is None)

        entry = responses.setdefault(resp_id, {
            "has_temp": False, "temp": None, "temp_null": False,
            "has_top_p": False, "top_p": None, "top_p_null": False,
        })
        # Se lo stesso response_id compare in più eventi SSE (es. response.created e response.done),
        # aggiorna o conserva senza duplicare.
        if has_temp:
            entry["has_temp"] = True
            if valid_temp is not None:
                entry["temp"] = valid_temp
            elif temp_is_null:
                entry["temp_null"] = True
        if has_top_p:
            entry["has_top_p"] = True
            if valid_top_p is not None:
                entry["top_p"] = valid_top_p
            elif top_p_is_null:
                entry["top_p_null"] = True

    # 1. Parsing di stderr.log (in particolare tracce SSE e log diagnostici Rust)
    for raw_line in stderr_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Estrai eventuale frammento SSE "data: ..."
        if "data:" in line:
            idx = line.find("data:")
            candidate_str = line[idx + 5:].strip()
            if candidate_str.startswith("{") and candidate_str.endswith("}"):
                try:
                    payload = json.loads(candidate_str)
                    _process_candidate(payload)
                except json.JSONDecodeError:
                    pass
        elif line.startswith("{") and line.endswith("}"):
            try:
                payload = json.loads(line)
                _process_candidate(payload)
            except json.JSONDecodeError:
                pass

    # 2. Parsing di events.jsonl (eventi strutturati di Codex / Inspect)
    for raw_line in events_text.splitlines():
        line = raw_line.strip()
        if not line or not (line.startswith("{") and line.endswith("}")):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            _process_candidate(event)

    # Sintesi dei valori osservati
    observed_temps: list[float] = []
    has_temp_null = False
    has_temp_present = False

    observed_top_ps: list[float] = []
    has_top_p_null = False
    has_top_p_present = False

    for resp in responses.values():
        if resp["has_temp"]:
            has_temp_present = True
            if resp["temp"] is not None:
                observed_temps.append(resp["temp"])
            elif resp["temp_null"]:
                has_temp_null = True
        if resp["has_top_p"]:
            has_top_p_present = True
            if resp["top_p"] is not None:
                observed_top_ps.append(resp["top_p"])
            elif resp["top_p_null"]:
                has_top_p_null = True

    distinct_temps = tuple(sorted(set(observed_temps)))
    distinct_top_ps = tuple(sorted(set(observed_top_ps)))

    # Valutazione temperature
    temp_status: str
    final_temp: float | None = None
    if len(distinct_temps) == 1:
        final_temp = distinct_temps[0]
        temp_status = "observed"
    elif len(distinct_temps) > 1:
        final_temp = None
        temp_status = "inconsistent"
    elif has_temp_null:
        temp_status = "explicit_null"
    elif has_temp_present:
        temp_status = "not_reported"
    else:
        temp_status = "unavailable"

    # Valutazione top_p
    top_p_status: str
    final_top_p: float | None = None
    if len(distinct_top_ps) == 1:
        final_top_p = distinct_top_ps[0]
        top_p_status = "observed"
    elif len(distinct_top_ps) > 1:
        final_top_p = None
        top_p_status = "inconsistent"
    elif has_top_p_null:
        top_p_status = "explicit_null"
    elif has_top_p_present:
        top_p_status = "not_reported"
    else:
        top_p_status = "unavailable"

    # Stato globale
    if temp_status == "inconsistent" or top_p_status == "inconsistent":
        overall_status = "inconsistent"
        source = "server_response"
        details = f"Rilevati valori discordanti: temperature={list(distinct_temps)}, top_p={list(distinct_top_ps)}"
    elif temp_status == "observed" or top_p_status == "observed":
        overall_status = "observed"
        source = "server_response"
        details = "Parametri di campionamento server-reported estratti dalla risposta del modello."
    elif temp_status == "explicit_null" or top_p_status == "explicit_null":
        overall_status = "explicit_null"
        source = "server_response"
        details = "Il server ha esplicitamente restituito null per i parametri di campionamento."
    elif temp_status == "not_reported" or top_p_status == "not_reported":
        overall_status = "not_reported"
        source = "server_response"
        details = "Risposta del modello ricevuta, ma i parametri di campionamento non compaiono nei metadati."
    else:
        overall_status = "unavailable"
        source = "none"
        if collection_mode == "passive":
            details = "Dati di campionamento non esposti dal backend in modalità passive."
        else:
            details = "Nessun dato di campionamento osservabile nei log."

    return SamplingTelemetry(
        temperature=final_temp,
        top_p=final_top_p,
        source=source,
        status=overall_status,
        transport=transport_detected,
        collection_mode=collection_mode,
        response_count=len(responses),
        distinct_temperatures=distinct_temps,
        distinct_top_p=distinct_top_ps,
        details=details,
    )


def extract_sampling_telemetry(
    logs_dir: Path,
    collection_mode: str = "passive",
    backend: str = "codex_cli",
) -> SamplingTelemetry:
    """Estrae la telemetria di campionamento leggendo i log in logs_dir."""
    stderr_file = logs_dir / "stderr.log"
    events_file = logs_dir / "events.jsonl"
    stderr_text = stderr_file.read_text(encoding="utf-8", errors="replace") if stderr_file.is_file() else ""
    events_text = events_file.read_text(encoding="utf-8", errors="replace") if events_file.is_file() else ""
    return parse_sampling_telemetry(
        stderr_text=stderr_text,
        events_text=events_text,
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
            response_count=int(data.get("response_count") or 0),
            distinct_temperatures=tuple(data.get("distinct_temperatures") or ()),
            distinct_top_p=tuple(data.get("distinct_top_p") or ()),
            client_requested_temperature=_validate_numeric(data.get("client_requested_temperature")),
            client_requested_top_p=_validate_numeric(data.get("client_requested_top_p")),
            details=data.get("details"),
        )
    except Exception:
        return None
