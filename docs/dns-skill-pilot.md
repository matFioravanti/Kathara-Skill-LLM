# Pilota Small per Kathara DNS v1/v2

La v1 originale resta in `skills/dns/SKILL.md`, con SHA-256
`241b4b6f0c8c72d30761bf5c237cfdc37aa23b5ef450845e7d4f23ca14f7aaf0`.
Il diff completo di `SKILL.md` è in [dns-skill-v1-v2.diff](dns-skill-v1-v2.diff).
La proposta per Creation è in [dns-v2-creation-proposal.md](dns-v2-creation-proposal.md).

La selezione esplicita avviene con `--config benchmark_dns_skill_v1.yaml` o
`--config benchmark_dns_skill_v2.yaml`. Tra le configurazioni cambia solo
`aut.dns_skill`. Il loader copia il singolo bundle scelto nel percorso canonico
`.codex/skills/kathara-dns/`. Le modalità forzate mantengono la stessa direttiva
e il protocollo esistente. In `auto` restano disponibili DNS e Creation senza
forzatura. La descrizione DNS usata per la scoperta è identica. `no_skill` e
`creation_only` conservano i loro mount e prompt, e sono fuori dal pilota.
Per eventuali controlli con quelle due modalità, usare la configurazione v1:
la fingerprint del benchmark include l'intera sezione `aut`, anche i percorsi
non montati.

Le due braccia usano ID e report diversi. Ciascuna contiene tre osservazioni
(lab_01, albero base, Small, prompt T1, ripetizione 1; dns_only, both_forced,
auto). Modello, reasoning effort, protocollo, laboratorio, prompt e checker
sono identici. È un controllo preliminare, non una stima dell'effetto.

Da eseguire dalla radice. Tenere `--dry-run` per l'anteprima statica e rimuoverlo
solo quando si vuole avviare il pilota. Su macOS si può anteporre `caffeinate -i`
al comando Python.

```bash
for variant in v1 v2; do
  .venv/bin/python -B -u scripts/run_experiment.py \
    "experiments/dns_skill_pilot_${variant}.yaml" \
    --config "benchmark_dns_skill_${variant}.yaml" \
    --report-output "results/general/dns_skill_pilot_${variant}" \
    --pipeline-mode phased \
    --generation-workers 1 \
    --checker-workers-small 1 \
    --resume --dry-run || break
done
```

Quando il pilota sarà eseguito, confrontare i risultati per prompt, modalità
e ripetizione, usando i soli tentativi inclusi e distinguendo gli esiti tecnici
da quelli del task. Confrontare anche controlli falliti, tempo e token.
