# Proposta per Kathara Creation

La Skill Creation corrente è il controllo del confronto e rimane invariata. Per una revisione futura separata, aggiungere una clausola di ambito all'inizio della procedura.

> Per una modifica DNS su un laboratorio esistente, usa solo le istruzioni di inventario pertinenti. Non ripartire dal flusso per creare un lab e non rigenerare lab.conf o gli startup. Lascia alla Skill DNS i file BIND, le configurazioni dei resolver e i comandi DNS. Se la richiesta include esplicitamente una fase di creazione, termina prima topologia, indirizzi e routing, poi consegna alla Skill DNS l'inventario effettivo. Coordina eventuali modifiche all'immagine e lascia la validazione dinamica a una fase autorizzata separata.

Questo chiarisce il conflitto in both_forced fra la procedura Creation per la costruzione di un nuovo lab e le modifiche DNS puntuali a un lab esistente. Una futura valutazione della proposta richiederà una condizione sperimentale separata.
