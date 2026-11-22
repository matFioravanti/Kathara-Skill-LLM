# Semantic precheck

For a regular hierarchy, derive a compact JSON observation outside the lab from the final files and the original task. Reuse the planned mapping for the expected fields only. Resolve includes and expand zone owners/targets (absolute lowercase names with trailing dots). Do not infer observed values from the plan. Use the manual gate for unresolved shell/BIND constructs and report uncertainty instead of guessing.

- `clients`: requested client → ordered nameserver IP list.
- `resolver_writes`: client → list of complete nameserver lists, in effective order from the mounted file through startup writes. Missing resolver configuration is an empty list. Review possible late writers separately.
- `servers`: assigned BIND device → `role` (`authority` or `resolver`), `addresses` (owned usable IP strings), `network_ready_at` (ordinal of final network prerequisite, 0 if already ready), `activations` (list of objects with ordinal `at` and `action` of `start` or `restart`). Add loopback in `addresses` and `verified_loopback` only with separate evidence of working local service. Confirm image, unit and effective config separately.
- `required_zones`: expected authoritative zone names. `artificial_root`: whether those zones belong to the same artificial hierarchy.
- `zones`: served zone → `soa_count` (apex SOA count), `apex_ns` (NS owner → IPs independently read from authoritative data for the required/usable glue families), `delegations` (child zone → object with `ns` list and `glue` map from NS owner to addresses). Include served ancestors. Check all independently configured copies and secondary configuration separately.
- `image_devices`: devices with approved image edits (used only with the baseline comparison).

Run `python3 <skill-dir>/scripts/static_audit.py <observations.json> --before <baseline> --after <lab>`. The comparison checks lab.conf except approved image entries and protects original startup prefixes. Review the full diff as required by the Skill, including image compatibility, new paths, metadata, and the exact startup additions. If an existing managed trailer was legitimately edited, compare the original portion separately. A passing precheck covers only supplied observations and cannot establish BIND syntax, routing or runtime behavior.

Optional resolved evidence extends the precheck without replacing the manual gates.

- Server `zone_types` maps declared zone names to BIND types; supply `recursion` as a Boolean with it. This checks standard isolated authority/resolver roles. Explicit mixed designs need manual review.
- `required_records` and `records` are supplied together, each mapping absolute normalized owner → type → list of canonical RDATA strings (MX includes preference and absolute exchange). Expected values come from the task, observed values from actual zone files.
- `gate_checks` optionally maps G1–G4 to lists of PASS/FAIL/UNVERIFIED results already established by actual checks. Include unavailable tools as UNVERIFIED. Empty lists are UNVERIFIED; FAIL takes precedence. These are evidence summaries, not a way to assert checks that were never performed.

Use only initial task/lab data, permitted references and the candidate files you generated. Never read correction.yaml, historical results, checker reports or reference solutions to construct observations. Record missing evidence as UNVERIFIED. Configuration completion, gate validation and external runtime validation remain separate.
