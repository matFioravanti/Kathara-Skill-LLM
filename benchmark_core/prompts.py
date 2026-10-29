"""Risoluzione e validazione centralizzata dei prompt sperimentali."""
from pathlib import Path
import ipaddress
import re
import yaml

PROMPT_TYPES = ("T1", "T2", "T3", "T4", "T5", "T6")


def render_task_prompt(root: Path, assignment, prompt_type: str) -> tuple[Path, str]:
    """Resolve explicit device/address bindings from the assignment's bindings.yaml."""
    from .task_catalog import task_correction_path
    source = resolve_prompt(root, assignment.dns_tree_id, prompt_type, assignment.task_level)
    text = source.read_text(encoding="utf-8")
    tokens = set(re.findall(r"\{\{\s*([A-Za-z0-9_-]+)\.(device|address)\s*\}\}", text))
    binding_file = task_correction_path(root, assignment).parent / "bindings.yaml"
    bindings = {}
    if binding_file.exists():
        if any(p.is_symlink() for p in (binding_file, *list(binding_file.parents)[:4])):
            raise ValueError(f"Binding con link simbolico: {binding_file}")
        try:
            bindings = yaml.safe_load(binding_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise ValueError(f"Binding non validi: {binding_file}: {exc}") from exc
        if not isinstance(bindings, dict):
            raise ValueError("bindings.yaml deve contenere un mapping")
    lab = root / "scenarios" / assignment.lab_id / "lab"
    conf = (lab / "lab.conf").read_text(encoding="utf-8")
    for name, binding in bindings.items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", name) or not isinstance(binding, dict) or set(binding) != {"device", "address"}:
            raise ValueError(f"Binding non valido: {name!r}")
        device, address = binding["device"], binding["address"]
        if not isinstance(device, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", device) or not re.search(rf"(?m)^\s*{re.escape(device)}\[\d+\]\s*=", conf):
            raise ValueError(f"Dispositivo binding assente dal lab: {device!r}")
        try:
            ip = ipaddress.ip_address(address)
            startup = (lab / f"{device}.startup").read_text(encoding="utf-8")
        except (ValueError, TypeError, OSError) as exc:
            raise ValueError(f"Indirizzo o startup binding non valido per {device}") from exc
        ips = set()
        for word in re.findall(r"[0-9A-Fa-f:.]+(?:/\d+)?", startup):
            try:
                ips.add(ipaddress.ip_interface(word).ip)
            except ValueError:
                pass
        if ip not in ips:
            raise ValueError(f"Indirizzo {address} non presente nello startup di {device}")
    for name, field in tokens:
        if name not in bindings:
            raise ValueError(f"Binding mancante: {name}")
        text = re.sub(r"\{\{\s*" + re.escape(name) + r"\." + field + r"\s*\}\}", str(bindings[name][field]), text)
    if "{{" in text or "}}" in text:
        raise ValueError(f"Segnaposto non risolto nel prompt: {source}")
    return source, text


def resolve_prompt(root: Path, scenario_id: str, prompt_type: str, task_level: str | None = None) -> Path:
    # task_level selects the new canonical layout; the two-argument legacy form
    # remains available to read historical tools and tests.
    if task_level is not None:
        from .task_catalog import prompt_path
        path = prompt_path(root, scenario_id, task_level, prompt_type)
        if any(p.is_symlink() for p in (path, path.parent, path.parent.parent)):
            raise ValueError(f"Prompt con link simbolico non supportato: {path}")
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ValueError(f"Prompt mancante o non leggibile: {path}") from exc
        if not content.strip():
            raise ValueError(f"Prompt vuoto: {path}")
        return path
    if prompt_type not in PROMPT_TYPES:
        raise ValueError(f"prompt_type non valido: {prompt_type!r}; valori ammessi: {', '.join(PROMPT_TYPES)}")
    scenario_dir = root / "prompt" / scenario_id
    if not scenario_dir.is_dir():
        raise ValueError(f"Directory prompt dello scenario '{scenario_id}' non trovata: {scenario_dir.relative_to(root)}")
    path = scenario_dir / f"{prompt_type}.md"
    if not path.is_file():
        raise ValueError(f"Missing prompt for scenario '{scenario_id}':\n{path.relative_to(root)}")
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"Prompt non leggibile per scenario '{scenario_id}': {path.relative_to(root)} ({exc})") from exc
    if not content.strip():
        raise ValueError(f"Prompt vuoto per scenario '{scenario_id}': {path.relative_to(root)}")
    return path


def missing_prompts(root: Path, scenario_ids, prompt_type: str) -> list[str]:
    from .task_catalog import TaskAssignment, prompt_path
    missing = []
    for scenario_id in scenario_ids:
        try:
            if isinstance(scenario_id, TaskAssignment):
                resolve_prompt(root, scenario_id.dns_tree_id, prompt_type, scenario_id.task_level)
            else:
                resolve_prompt(root, scenario_id, prompt_type)
        except ValueError:
            if isinstance(scenario_id, TaskAssignment):
                missing.append(prompt_path(root, scenario_id.dns_tree_id, scenario_id.task_level, prompt_type).relative_to(root).as_posix())
            else:
                missing.append(f"prompt/{scenario_id}/{prompt_type}.md")
    return missing
