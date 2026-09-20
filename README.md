# Kathara Skill LLM Benchmark

Benchmark riproducibile per Codex CLI che configura DNS e servizi web opzionali in laboratori Kathara. Ogni generazione viene eseguita dall'eseguibile `codex` installato sul Mac host e riutilizza esclusivamente il login ChatGPT già presente nella CLI.

## Architettura

Ogni scenario contiene soltanto un prompt e un laboratorio iniziale immutabile. Per ciascuna ripetizione il runner conserva il baseline in `runs/<run_id>/input/lab`, crea la copia modificabile in `runs/<run_id>/lab` e avvia l'Agent Under Test (AUT) sul Mac host con `codex exec`. `run/lab` è la working directory della CLI e Codex usa il proprio sandbox `workspace-write`.

Terminata la prima esecuzione, il runner salva gli eventi JSONL nativi di Codex, chiude la finestra di misurazione e calcola il diff rispetto al laboratorio originale. Una seconda esecuzione Codex, con log separati, legge il laboratorio finale protetto, il prompt originale, la skill del checker e lo schema. Questa chiamata produce `correction.yaml`; le sue metriche non entrano mai nei risultati AUT.

Prima e dopo la seconda chiamata viene calcolato l'hash ricorsivo del laboratorio. Un cambiamento causa `CORRECTION_GENERATION_FAILED` e il ripristino dalla copia temporanea protetta. `kathara-lab-checker` opera su un'altra copia temporanea del laboratorio finale, perché scrive i report nella directory del laboratorio; la copia viene eliminata anche in caso di errore e soltanto i report sono conservati in `run/results/`.

Il risultato finale deriva esclusivamente dal checker. Un'esecuzione Codex riuscita può quindi avere `aut_execution_success=true`, `checker_execution_success=true` e `task_success=false`. Se la correction o il checker falliscono per un problema infrastrutturale, `task_success` rimane nullo.

```text
scenario -> copia lab -> Codex CLI AUT -> eventi JSONL + diff
                                        |
                                        v
                     Codex CLI correction generator
                                        |
                                        v
                    correction.yaml -> copia lab -> checker
                                                      |
                                                      v
                              runs/ (grezzi) -> results/ (derivati)
```

`codex exec --json --ephemeral --sandbox workspace-write --skip-git-repo-check -C <workspace> -` esegue Codex senza API key, passa il prompt via stdin e conserva tutti gli eventi JSONL. Kathara Lab Checker avvia il laboratorio e determina il superamento dei check senza un LLM judge. Inspect AI e Inspect SWE rimangono tra le dipendenze dell'ambiente per compatibilità e validazione delle skill, ma non sono coinvolti nell'esecuzione, nel provider o nell'autenticazione di Codex.

## Requisiti e installazione

Servono Python 3.11 o successivo, Docker con daemon attivo, Kathara e Codex CLI installata e autenticata con ChatGPT. L'ambiente verificato durante la creazione usa Python 3.14.6.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

`requirements.txt` è il freeze dell'ambiente risolto. Le versioni centrali sono Inspect AI 0.3.266, Inspect SWE 0.2.71, kathara-lab-checker 0.1.14, Kathara 3.8.3, pandas 3.0.6 e PyYAML 6.0.3.

Non impostare `OPENAI_API_KEY`, `CODEX_API_KEY` o `INSPECT_EVAL_MODEL`: il runner le rimuove soltanto dalla copia dell'environment passata al subprocess, senza modificare l'ambiente dell'utente. Se `CODEX_HOME` è già presente viene preservato; altrimenti Codex usa la configurazione standard, incluso il login ChatGPT locale.

La configurazione predefinita seleziona `gpt-5.6-terra` con reasoning effort `low`, una combinazione verificata con la CLI locale installata. `correction_generator.model` e `reasoning_effort` a `null` ereditano gli stessi valori dell'AUT. Un valore `null` per `aut.model` usa il modello predefinito dell'account Codex; il runner passa `-c model_reasoning_effort="…"` solo se configurato. La versione di Codex installata viene verificata dal preflight.

## Skill richieste

Il repository predispone le directory ma non inventa il contenuto delle skill, che deve essere fornito dall'esperimento:

```text
skills/dns/SKILL.md
skills/lab_checker/SKILL.md
skills/lab_checker/config-schema.md
```

Le due skill devono avere frontmatter compatibile con la specifica Agent Skills (`name` e `description`). La prima è visibile soltanto all'AUT. La seconda è visibile soltanto al correction generator; lo schema viene montato separatamente in sola lettura. Per verificare presenza e validità:

```bash
python scripts/run_benchmark.py --check-skills
```

L'assenza di uno di questi file produce un errore esplicito prima di qualsiasi chiamata modello.

## Scenari

Gli scenari vengono scoperti automaticamente sotto `scenarios/` e sono validi quando contengono:

```text
scenarios/<scenario_id>/
├── prompt.txt
└── lab/
    └── lab.conf
```

Non aggiungere `scenario.yaml` o `correction.yaml`. Il prompt è la fonte normativa; `lab/` è copiato per ogni run e non viene modificato. `example_dns_001` è uno scenario strutturale pronto per l'esecuzione dopo l'aggiunta delle skill.

## Esecuzione

Il preflight controlla skill, `which codex`, `codex --version`, `codex login status`, Docker, Compose, Kathara e checker senza fare chiamate al modello:

```bash
python scripts/run_benchmark.py --preflight --agent codex
```

Eseguire uno scenario:

```bash
python scripts/run_benchmark.py --scenario example_dns_001 --agent codex
```

Eseguire cinque ripetizioni di tutti gli scenari:

```bash
python scripts/run_benchmark.py --all --agent codex --repetitions 5
```

`benchmark.continue_on_error` decide se continuare dopo una run infrastrutturalmente fallita. Una soluzione AUT valutata e bocciata dal checker è una run completata, non un errore del comando.

## Artefatti e stati

Ogni run usa un ID leggibile e univoco, per esempio `example_dns_001__codex__r001__20260920T131500000000Z_ab12cd34`, e conserva:

```text
runs/<run_id>/
├── manifest.json
├── input/
│   ├── lab/          # baseline originale immutabile
│   └── prompt.md
├── lab/              # unica copia modificabile — before → after AUT
├── correction.yaml
├── results/          # report CSV del checker
└── logs/
    ├── aut/          # events.jsonl, stderr.log, result.json, invocation.json, prompt.txt
    ├── generator/    # log Codex del correction generator
    ├── generator_output/  # correction.yaml candidata prima della validazione
    ├── diff.json
    ├── lab_integrity.json
    ├── checker_invocation.json
    ├── checker_execution.json
    ├── checker_stdout.log
    └── checker_stderr.log
```

`manifest.json` registra identificatori, timestamp, versioni, hash delle skill, stato e riferimenti agli artefatti. Registra inoltre `execution_backend: codex_cli`, `authentication: local_chatgpt_login` e `api_key_used: false`. Gli stati sono `PENDING`, `AUT_RUNNING`, `AUT_FAILED`, `AUT_COMPLETED`, `CORRECTION_GENERATION_FAILED`, `CHECKER_FAILED` e `COMPLETED`.

`runs/` è la fonte persistente: contiene log Codex AUT, lab finale (`lab/`), baseline (`input/lab/`), diff, correction e report. `results/` contiene soltanto CSV derivati e può essere ricostruita in qualunque momento. Per ogni run esistono persistentemente solo due versioni del laboratorio: `input/lab` (before) e `lab` (after).

## Aggregazione e analisi

```bash
python scripts/aggregate_results.py
python scripts/analyze_results.py
```

`benchmark_results.csv` contiene una riga per run e unisce stati, risultato del checker, pass rate per categoria ricostruibile, metriche Codex AUT e diff. `benchmark_detailed.csv` contiene una riga per check usando le colonne reali di kathara-lab-checker 0.1.14: `Test Description`, `Passed` e `Reason`.

Gli eventi `codex exec --json` sono conservati in `logs/aut/events.jsonl`. Il parser legge `turn.completed.usage` quando disponibile, il messaggio finale, turni e tool nativi. Il costo API e le metriche che Codex non emette restano nulli: non vengono inventati né calcolati costi. Le metriche della seconda esecuzione non vengono lette dall'aggregatore.

L'analisi produce `analysis_summary.csv`, con una riga globale e righe per esperimento (scenario, agent, modello e hash della skill). Riporta denominatori, success rate, medie, mediane e deviazioni standard quando sono disponibili più osservazioni.

## Smoke check

```bash
python scripts/smoke_check.py
```

Lo smoke check importa i package, carica la configurazione, scopre gli scenari, risolve `codex_cli()`, valida la sintassi Python, crea un workspace temporaneo, verifica diff e immutabilità, aggrega una directory vuota e usa i writer reali del checker per controllare il parser dei report. Non avvia Docker, Kathara o chiamate LLM; elimina automaticamente gli artefatti temporanei.

## Altri agent

Questo benchmark supporta intenzionalmente soltanto Codex CLI locale. Non usa fallback automatici verso OpenAI API, Inspect model provider, Anthropic, Gemini o altri provider. Un eventuale backend aggiuntivo deve essere una scelta esplicita e non può essere usato come fallback.
