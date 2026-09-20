---
name: kathara-lab-checker
description: >
  Generate and run a kathara-lab-checker configuration (correction.yaml) from a Kathara lab
  prompt or existing lab files. Use this skill whenever the user asks to: check, grade,
  validate, or auto-correct a Kathara lab or student submission; generate a checker
  configuration from a lab spec/prompt; run kathara-lab-checker; or produce a correction
  file for an exam or homework scenario. Trigger even when the user says "checker config",
  "correction file", "auto-grade", or "validate student labs". Works hand-in-hand with the
  kathara-lab-creation skill: the structured prompt produced by that skill is the primary
  input for this one.
---

# Kathara Lab Checker

Generate a `correction.yaml` configuration for
[kathara-lab-checker](https://github.com/KatharaFramework/kathara-lab-checker) from a Kathara
lab specification or prompt. Optionally install the tool and run it against a directory of
student submissions. **Always prefer YAML** (`correction.yaml`) over JSON; only use JSON if
the user explicitly requests it.

## Tool overview

`kathara-lab-checker` reads one configuration file and a directory of student labs, starts
each lab, runs the declared checks, and writes per-lab report files plus a combined
`results.xlsx` / `results.csv`.

```
python3 -m kathara_lab_checker \
  --config <correction.yaml> \
  --labs   <path-to-labs-directory> \
  [--no-cache] \
  [--report-type excel|csv|none]
```

Install (Python ≥ 3.11 required):
```
python3 -m pip install kathara-lab-checker
```

## Primary input: the lab prompt

The best input for this skill is the **structured prompt** produced by the
`kathara-lab-creation` skill (steps 2–3 of that skill's procedure). That prompt already
contains devices, collision domains, IP/MAC plan, images, routing protocols, and validation
goals — everything needed to build a complete checker config.

If no structured prompt is available, extract the same information from:
- an existing `lab.conf` + `.startup` files
- a natural-language lab description
- a PDF/docx assignment sheet

## Configuration file format

**Use YAML by default** (`correction.yaml`). YAML is more readable, supports comments, and
allows embedding the lab topology inline via `lab_inline`. See
`references/config-schema.md` for the full annotated schema with all fields and their
semantics.

### Top-level fields

| Field              | Type    | Purpose |
|--------------------|---------|---------|
| `lab_inline`       | string  | Topology-only inline content (YAML only): device-to-collision-domain mappings, no image declarations — use instead of a separate `structure` file |
| `labs_path`        | string  | Path to the directory of student labs (can be omitted if passed via CLI) |
| `convergence_time` | int     | Seconds to wait for routing convergence before running checks |
| `structure`        | string  | Path to a `lab.conf`-formatted file declaring the expected topology (alternative to `lab_inline`) |
| `default_image`    | string  | Kathara image used when a student lab does not specify one |
| `test`             | object  | All check declarations (see below) |

### Check blocks inside `test`

See `references/config-schema.md` for the complete schema. Quick reference:

- `requiring_startup` — list of device names that must have a `.startup` file
- `ip_mapping` — per-device, per-interface expected `ip/prefix`
- `daemons` — per-device list of daemons that must (`name`) or must not (`!name`) be running
- `kernel_routes` — per-device list of expected routes in the data-plane
- `protocols.bgpd.neighbors` — list of `{ip, asn}` peers that must be established
- `protocols.bgpd.networks` — prefixes the device must announce in BGP
- `protocols.<proto>.injections` — protocols redistributed into (or excluded from) another
- `applications.dns` — DNS authority, local-NS, and record checks
- `reachability` — per-device list of IPs or DNS names that must be ping-reachable
- `custom_commands` — arbitrary commands with `regex_match`, `output`, or `exit_code` assertions

## Workflow

The workflow is strictly interactive. Follow the steps in order and never skip ahead.

---

### Step 1 — Receive the prompt

The user provides the lab prompt (typically the structured output of `kathara-lab-creation`).
Accept it and move to step 2.

---

### Step 2 — Inspect the lab files (if available)

If the user has provided a path to an existing lab directory, read:
- `lab.conf` — topology and image declarations
- every `.startup` file — to infer daemons, IP configuration, routing protocol setup,
  DNS configuration, and any other service

Use this information to make the check derivation in step 3 more accurate. If no lab
files are provided, proceed with the prompt alone.

---

### Step 3 — Derive available checks

Analyse the prompt (and lab files if present) and determine which of the following checks
can be configured for this scenario. For each check, note which devices and values would
be involved. Do not ask the user anything yet — this step is internal analysis only.

Checks to evaluate:

| Check | Applicable when |
|---|---|
| `requiring_startup` | Any device with a `.startup` file |
| `ip_mapping` | Any device with static IP addresses |
| `daemons` | Any device running or explicitly not running a known daemon |
| `kernel_routes` | Any device with a routing table (routers + hosts with a gateway) |
| `protocols.bgpd` | BGP speakers present |
| `protocols.ripd` | RIP configured |
| `protocols.ospfd` | OSPF configured |
| `protocols.*.injections` | Redistribution between protocols configured |
| `applications.dns` | BIND or dnsmasq present |
| `applications.http` | Web server present |
| `reachability` | End-to-end connectivity is a lab goal |

---

### Step 4 — Ask the user which checks to configure

Before presenting the interactive list, write a brief prose paragraph (2–4 sentences)
in the conversation explaining what checks were found and why — so the user has context
before they click. Then use the `ask_user_input` tool with `type: multi_select` to
present the applicable checks as clickable options.

Each option label must follow this format:
```
<check_name> — <one-line summary of what is checked and on which devices>
```

Example call (adapt labels to the actual lab):
```
ask_user_input(questions=[{
  "question": "Quali check vuoi includere nella correction.yaml?",
  "type": "multi_select",
  "options": [
    "requiring_startup — r1, r2, pc1, pc2 must have a .startup file",
    "ip_mapping — IP addresses on all interfaces of r1, r2, pc1, pc2",
    "daemons — ripd + zebra running on r1 and r2; not running on pc1, pc2",
    "kernel_routes — full routing table after RIP convergence on r1, r2",
    "protocols.ripd — connected routes redistributed into RIP on r1, r2",
    "reachability — full mesh reachability across all subnets"
  ]
}])
```

Only include options for checks that are actually applicable (derived in step 3).
Do not include checks for protocols or services not present in the lab.
Wait for the user's selection before proceeding to step 5.

---

### Step 5 — Configure the selected checks

For each check selected by the user, derive the full configuration from the prompt and
lab files. Do not ask further questions for standard checks — infer all values directly.

Apply the following derivation rules:

**`requiring_startup`**: every device that has or must have a `.startup` file.

**`ip_mapping`**: for each device, every interface by number (`"0"`, `"1"`, …) and its
`ip/prefix`. Use the IP plan from the prompt verbatim.

**`daemons`**: daemons implied by the image and startup content. Prefix `!` for daemons
that must not run (e.g. `!ripd` on pure hosts).

**`kernel_routes`**: only routes learned via routing protocols (RIP, OSPF, BGP, static
`ip route add`) — do **not** include directly-connected subnets. Linux installs
connected subnets as `proto kernel scope link` entries when an IP is assigned to an
interface; the checker does not count these, so listing them causes false failures
("wrong number of routes" + "missing route X"). Hosts that set a default gateway via
`ip route add default via ...` should list only `0.0.0.0/0`, not their own subnet.

**`protocols.bgpd`**: `neighbors` (ip + asn), `networks` (announced prefixes), and
`injections` (redistribution into/from BGP).

**`protocols.<ripd|ospfd>.injections`**: redistributed protocols. Prefix `!` for
protocols that must not be redistributed.

**`applications.dns`**: `authoritative` (zone → server IPs), `local_ns` (resolver IP →
device names), `records` (type → name → value).

**`reachability`**: for a fully-connected scenario, all IPs in the address plan per
device. For partial scenarios, only IPs that device should reach.

**`lab_inline`**: topology-only — device-to-collision-domain mappings, no image
declarations. Images go in `default_image` at the top level.

**`convergence_time`**: 10 s for static-only labs; 60 s for IGP; 90 s for BGP or
mixed BGP+IGP.

---

### Step 6 — Ask about custom checks

After configuring all selected standard checks, ask:

> "Are there any additional custom checks (`custom_commands`) you want to add?
> These can assert arbitrary command output, regex matches, or exit codes inside
> any device."

If the user answers **yes**, collect each custom check interactively, one at a time:

For each custom check ask:
1. **Device**: which device should the command run on?
2. **Command**: what command to execute?
3. **Assertion**: should it match a regex, produce exact output, or return a specific
   exit code? (collect the expected value)

Repeat until the user says there are no more custom checks.

If the user answers **no**, skip this step.

---

### Step 7 — Write and present the file

Output the complete `correction.yaml`. Use YAML block style for readability. Add inline
comments to explain non-obvious values (e.g. `convergence_time` rationale, assumptions).

Present the file to the user for review.

---

### Step 8 — Validate and run (optional)

If the tool is installed and a reference lab is available, offer to validate:

```bash
python3 -m kathara_lab_checker \
  --config correction.yaml \
  --labs   <reference-lab-parent-dir> \
  --no-cache \
  --report-type none
```

Once validated, run against student submissions:

```bash
python3 -m kathara_lab_checker \
  --config correction.yaml \
  --labs   <student-labs-directory> \
  --report-type excel
```

## Completion criteria

A checker configuration is complete when:

1. The user has confirmed which checks to include (step 4 completed).
2. All devices from the lab prompt appear in at least one selected check block.
3. Every interface in the IP plan is covered by `ip_mapping` (if selected).
4. Routing protocol daemons are in `daemons` for every router that runs them (if selected).
5. `kernel_routes` lists all routes expected after convergence (if selected).
6. The topology is declared via `lab_inline` with topology-only content (no image declarations).
7. Custom checks have been fully specified with device, command, and assertion (if any).
8. The config file is syntactically valid YAML.

## Reference files

- `references/config-schema.md` — Full annotated schema for every field and check type,
  with YAML-first examples.