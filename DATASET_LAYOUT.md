# Preparazione dei dati del benchmark DNS

Le directory sono predisposte per l'inserimento manuale dei dati. I file
`.gitkeep` sono soltanto segnaposto per Git e possono essere eliminati quando
le rispettive directory contengono file reali. La presenza di una directory
non abilita una combinazione nell'esperimento e non valida una correction.

Ogni laboratorio ha una sola dimensione: `lab_01` → `small`, `lab_02` →
`medium`, `lab_03` → `large`. Ognuno può usare gli alberi `aster`, `aurora`
e `meridian`, per un massimo di nove triple; l'esperimento deve dichiarare
esplicitamente quelle per cui i dati sono disponibili. Con 9 triple, 5
prompt, 5 modalità Skill e una ripetizione la matrice avrebbe 225 run.

```text
scenarios/
├── lab_01/{lab/,tasks/{aster,aurora,meridian}/small/}
├── lab_02/{lab/,tasks/{aster,aurora,meridian}/medium/}
└── lab_03/{lab/,tasks/{aster,aurora,meridian}/large/}
```

- **Prompt:** inserire `T1.md`, `T2.md`, `T3.md`, `T4.md` e `T5.md` in
  `prompt/<dns_tree_id>/<task_level>/`, per esempio
  `prompt/aurora/small/T1.md`. T6 è facoltativo. Le formulazioni per la stessa
  coppia albero–livello devono descrivere la stessa soluzione funzionale.
- **Laboratori:** inserire ogni baseline completa in `scenarios/<lab_id>/lab/`,
  compresi `lab.conf`, gli script `.startup` e le eventuali configurazioni
  persistenti. La baseline non deve contenere la correction. Le directory
  `lab_01`, `lab_02` e `lab_03` sono predisposte ma non ancora laboratori validi.
- **Correction:** inserire `correction.yaml` in
  `scenarios/<lab_id>/tasks/<dns_tree_id>/<task_level>/`. La stessa correction
  è condivisa da tutte le formulazioni e modalità Skill della stessa tripla e
  deve rispettare lo schema del Kathara Lab Checker.
- **Binding facoltativi:** inserire `bindings.yaml` accanto alla correction,
  per le assegnazioni esplicite di dispositivi e indirizzi ai segnaposto del
  prompt. Il formato supportato dal motore è:

  ```yaml
  server:
    device: pc1
    address: 192.0.2.1
  ```

  I segnaposto corrispondenti sono `{{server.device}}` e
  `{{server.address}}`. Il dispositivo deve essere presente nel `lab.conf` e
  l'indirizzo nello script di startup del dispositivo. L'esempio illustra il
  formato; non definisce un laboratorio o un'assegnazione reale.

Per abilitare un esperimento servono una baseline completa, i prompt non vuoti
per ogni formulazione selezionata, una correction valida e compatibile per
ogni tripla, gli eventuali binding necessari e le risorse Skill e runtime
richieste dalla configurazione. Occorre verificare manualmente l'equivalenza
funzionale dei prompt e la compatibilità dei requisiti DNS con il laboratorio.

In `experiments/thesis_final.yaml` aggiungere sotto `assignments` soltanto le
triple effettivamente disponibili e verificate. Per esempio, la seguente
sintassi dichiara due coppie compatibili; l'esempio non abilita dati reali:

```yaml
assignments:
  - lab_id: lab_01
    dns_tree_id: aurora
    task_levels: [small]
  - lab_id: lab_02
    dns_tree_id: aurora
    task_levels: [medium]
```

Aggiungere altre voci per altre coppie laboratorio–albero compatibili, quindi
selezionare `prompt_types`, `skill_modes` e `repetitions`. Con le risorse
inserite, verificare il piano senza avviare Kathara o l'agente:

```sh
.venv/bin/python scripts/run_experiment.py experiments/thesis_final.yaml --dry-run
```

Le configurazioni fornite non sono eseguibili fino all'inserimento dei dati e
delle assegnazioni; la sola struttura di cartelle non costituisce un dataset.
