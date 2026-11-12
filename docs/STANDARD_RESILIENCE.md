# Continuità del benchmark standard

Questa supervisione si applica a `run_experiment.py` e al percorso legacy di
`run_benchmark.py`. COST266 usa il proprio runner e non importa questi moduli.
Prompt, Skill, gate, checker, classificazione scientifica e contabilità token
restano quelli esistenti. Un task scorretto con checker completato è una run
COMPLETED e non viene rigenerato per migliorarne il punteggio.

## Esecuzione e ripresa

Le CLI esistenti continuano a funzionare:

```bash
.venv/bin/python scripts/run_experiment.py experiments/thesis_final.yaml
.venv/bin/python scripts/run_experiment.py experiments/thesis_final.yaml --resume
.venv/bin/python scripts/run_experiment.py experiments/thesis_final.yaml --dry-run
.venv/bin/python scripts/run_benchmark.py --experiment experiments/thesis_final.yaml --resume
.venv/bin/python scripts/run_benchmark.py --scenario lab_01 --prompt-type T1 --skill-mode dns_only
```

La ripresa automatica è attiva per impostazione predefinita. Un'osservazione
completata viene riutilizzata soltanto dopo la verifica di condizioni, baseline,
output, snapshot correction, metriche e report. Cambiare prompt, Skill, modello,
effort o altre condizioni confrontabili richiede un nuovo esperimento.

Se l'AUT è terminato e il laboratorio finale ha l'hash registrato, il recupero
ripete solo il checker. Un AUT interrotto viene ritentato dalla baseline in una
nuova directory fisica; gli artefatti parziali restano conservati. La semantica
della sessione Codex non viene ricostruita artificialmente. Le run COMPLETED
duplicate o ambigue restano errori di integrità.

`runs/.supervision/<identità>/checkpoint.json` è il registro atomico persistente:
contiene condizioni originali, tentativi, tempi, errori classificati e percorsi.
`heartbeat.json` contiene PID, RAM RSS osservata e tempo trascorso. I journal
`worker_NNN.json` registrano le sole identità delle risorse create, mai stdin,
token o risposte account. Dopo un crash fra manifest e checkpoint il registro
viene riconciliato. I limiti dei tentativi persistono fra riavvii: riavviare la
CLI non azzera il budget. Per nuove prove usare una nuova ripetizione/identità.

## Configurazione

Sezione facoltativa in `benchmark.yaml` (valori predefiniti):

```yaml
resilience:
  auto_resume: true
  max_attempts: 3
  backoff_seconds: 5
  backoff_max_seconds: 60
  heartbeat_seconds: 10
  worker_timeout_seconds: 2400
  idle_timeout_seconds: 0
  memory_limit_mb: 4096
  cleanup_grace_seconds: 90
  auth_max_attempts: 3
  auth_wait_seconds: 300
  auth_poll_seconds: 15
```

`benchmark.timeout_seconds` conserva il limite per chiamata AUT/checker del
protocollo. Il watchdog aggiunge un limite complessivo al worker, inclusi setup
e raccolta degli artefatti: dimensionarlo per AUT + checker + cleanup.
`idle_timeout_seconds: 0` disabilita il timeout per assenza di scritture: un
modello/checker silenzioso può essere ancora attivo. Il controllo RAM RSS include
il worker e i subprocess visibili sull'host; non misura la memoria delle VM
Docker. `memory_limit_mb: 0` disabilita questa soglia.

Ogni tentativo usa un processo isolato, che termina e rilascia la propria RAM.
Il genitore non accumula gli output nativi dei modelli. La UI legacy conserva
al massimo gli ultimi 20 riepiloghi; tutti i risultati rimangono su disco.
Il watchdog invia SIGINT per consentire il cleanup, attende la grazia e infine
termina i processi residui. Il worker rileva anche la morte del supervisore.
I journal permettono la pulizia mirata delle sandbox create e dei laboratori
Kathara temporanei. Non vengono eseguiti prune o pulizie Docker globali.

I report sono pubblicati dopo ogni osservazione, con retry limitati per errori
tecnici di pubblicazione. Se la pubblicazione rimane impossibile, le run restano
conservate e `runs/.supervision/report_failure.json` indica REPORT_PENDING.
Si possono rigenerare offline con `scripts/aggregate_results.py`.

## Autenticazione

Il rilevamento di AUTH_FAILED comprende sessione scaduta, 401 e refresh revocato.
Il tentativo fallito termina e viene ripulito prima di qualsiasi recupero.
Un lock di sistema condiviso serializza worker e recupero di tutte le CLI
standard di questo utente. Il refresh usa l'API ufficiale app-server
`account/read` con `refreshToken: true`, dopo initialize/initialized. Non viene
avviato alcun turno modello durante il refresh e non vengono letti/copiati
manualmente auth.json, refresh token o chiavi. Il recupero non cambia account,
provider, modalità Skill, modello o autenticazione verso API key.

Fonti ufficiali:
- https://learn.chatgpt.com/docs/app-server
- https://learn.chatgpt.com/docs/auth?surface=cli

Un refresh riuscito fa partire un nuovo processo Codex; il tentativo riparte
dalla baseline e conserva integralmente quello fallito. Con docker_sandbox si
crea una nuova sandbox usando il broker OAuth già configurato: il login host
non è prova che il broker sbx abbia una sessione valida. Il successivo tentativo
AUT resta il controllo effettivo, entro il budget. Nessuna credenziale viene
copiata nella sandbox e non vengono riavviati daemon condivisi.

Se il refresh non è disponibile nella versione installata, la sessione è
revocata o il broker necessita una nuova autorizzazione, viene salvato
WAITING_AUTH. Il processo controlla il ripristino entro una finestra finita;
`auth_max_attempts` limita i cicli di recupero e `auth_wait_seconds` la durata di
ciascuna attesa. È possibile eseguire `codex login` in un altro terminale:
se la sessione è ripristinabile entro la finestra il lavoro riprende da solo.
Scaduto il budget, il checkpoint rimane disponibile. Le celle successive non
avviano generazioni finché il blocco auth non è risolto. Dopo il login si può
rilanciare la stessa CLI: le osservazioni già completate vengono saltate.
Login interattivo, MFA e consenso richiedono l'utente quando imposti dal provider.

## Verifiche e limiti

I test usano fixture, backend simulati e subprocess Python fittizi. Nessuna
chiamata reale a Codex o benchmark completo è necessaria. È comunque richiesto
un collaudo operativo separato per verificare refresh/broker della specifica
installazione e carichi di centinaia di run reali. Un arresto del sistema mentre
il disco non è disponibile può impedire anche il salvataggio di un checkpoint;
le pubblicazioni atomiche conservano l'ultima versione valida.

La supervisione richiede un sistema POSIX (macOS/Linux), `fork`, lock flock e
lettura dei processi con ps. Un'applicazione che importi direttamente
`pipeline.run_one` continua a usare la primitiva originale; per la supervisione
usare le CLI standard o `standard_runtime.run_supervised`.
