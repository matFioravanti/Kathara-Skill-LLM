# lab02_star7_mixed — DNS interno

La topologia e il routing originali rimangono invariati. `pc2` offre la root artificiale, `pc3`/`pc9` il primario/secondario di `test.`, `pc12` la zona delegata `services.test.`, e `pc11` il solo resolver ricorsivo per `pc4` e `pc6`.

Avvio: `kathara lstart`. Verifica dai client: `dig www.test.`, `dig status.services.test.`, quindi `curl http://www.test.` (pc4) oppure `curl http://portal.test.` (pc6).
