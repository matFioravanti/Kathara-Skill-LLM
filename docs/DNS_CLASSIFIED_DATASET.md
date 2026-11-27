# Dataset consolidato DNS

```bash
.venv/bin/python -B -u scripts/build_classified_dns_benchmark.py
```

Scrive il workbook e `validation.json` in
`outputs/dns_skill_pilot_v2_classified/`. Il consolidamento è offline e scrive
solo sotto `outputs/`: non avvia Kathara né il modello. La scrittura Excel e
la verifica XML sono in streaming; i controlli intermedi risiedono in un
database SQLite temporaneo. `--max-sheet-rows` permette di verificare la
suddivisione dei fogli con fixture piccole.

## Fonti e unità di osservazione

`Runs` contiene una riga per generazione fisica originale. Tutti i campi del
report originale, le metriche normalizzate e i JSON originali appiattiti e
integrali sono conservati. Le metriche della valutazione V3 selezionata
terminano in `_v3`. Le rivalutazioni non aggiungono righe a `Runs`.

Ogni riga di `Checks_All_XX` corrisponde a un risultato CSV o a una definizione
prevista senza risultato. `row_origin` distingue i due casi. `source_csv_row`
è il numero del record CSV logico (header=1), non una riga fisica del file:
le celle dei CSV possono contenere newline. `passed`, `check_status` ed
`error_present` conservano separatamente PASS, FAIL, NOT_EXECUTED e UNKNOWN.
I valori mancanti non sono trasformati in zeri.

Le revisioni originali e i tentativi V3 precedenti rimangono nei dettagli con
una `correction_version` distinta e `analysis_included=False`. I riepiloghi
principali includono solo le valutazioni correnti e la V3 selezionata per
ogni generazione. Si preferisce un report V3 completo, poi una valutazione
completata, poi la data più recente. Eventuali tentativi aggiuntivi sono
segnalati in Validation. `Evaluation_Metadata` conserva tutti i metadati delle
valutazioni, incluse quelle storiche.

## Classificazione e incertezza

I codici CS e DNS provengono dai commenti delle correction. La classificazione
usa lo snapshot della specifica valutazione, verificato con SHA-256, e le
definizioni del checker: dispositivi, parametri attesi, comandi e descrizioni.
La posizione dei risultati non è una chiave di associazione.

Il checker originale scrive `Checking correctness of DNS records` e `OK`
per molti risultati DNS superati, senza identificare client, nome o tipo di
record. Queste righe sono UNCLASSIFIED anche se l'esito PASS è certo. Nei
fallimenti, la motivazione spesso permette di recuperare i parametri esatti.
I controlli impliciti di esistenza e topologia delle V3 non hanno codici
espliciti nei commenti V3: conservano la categoria, con codice UNCLASSIFIED.
Non viene trasferito arbitrariamente un codice CS dalla correction originale.

`common_control_id` segnala solo definizioni con descrizione, dispositivo,
comando, tipo di record e risultato atteso esattamente uguali. Non attesta
equivalenza semantica di comandi differenti. Conservare `task_level` nei join.

Per un codice noto, `expected_checks` deriva dalla correction;
`unattributed_expected_checks` indica le definizioni che non possono essere
associate ai risultati generici. Il gruppo UNCLASSIFIED contiene quei
risultati osservati. I conteggi attesi per codice non vanno quindi sommati
con il gruppo UNCLASSIFIED come se rappresentassero insiemi disgiunti.
I conteggi eseguiti e gli esiti importati possono invece essere ricostruiti
dalle righe CSV di Checks_All. Nessuna presenza/assenza dell'errore viene
dedotta quando l'attribuzione rimane incerta.

La frequenza dell'errore nelle run usa come denominatore solo le run con
presenza dell'errore determinabile. La percentuale di fallimento dei controlli
usa i soli controlli eseguiti. Gli errori tecnici sono conservati nei metadati
e in Validation e non diventano errori funzionali del modello.
Per CS10/CS11, i fallimenti sono più facilmente identificabili dei successi:
le frequenze per codice sono quindi condizionate dall'identificabilità e non
vanno interpretate come una stima imparziale della prevalenza degli errori.

## Verifica

Il JSON elenca sorgenti e hash, anomalie, politiche e conteggi dei fogli.
I riepiloghi CSV del checker, i dettagli e le metriche vengono confrontati.
L'inventario delle generazioni e gli hash degli input sono ricontrollati
prima della pubblicazione. Tutti i fogli XLSX vengono riletti come XML per
verificare conteggi e assenza di celle con errori/formule involontarie.
Testi superiori al limite Excel sono conservati a frammenti in `Long_Text`.

I risultati sono una fotografia dei dati disponibili: rieseguire il comando
quando saranno completate ulteriori valutazioni. Non sommare originali,
V3 e revisioni storiche per stimare il numero di generazioni indipendenti.
