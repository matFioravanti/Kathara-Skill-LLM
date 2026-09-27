# Lab IPv4/IPv6 con 7 router e routing statico

Espansione del lab originale: mantiene `r1`–`r5`, `pc1`–`pc10` e tutti i collegamenti esistenti, aggiungendo `r6`, `r7` e `pc11`–`pc14`. Il routing resta esclusivamente statico sia IPv4 sia IPv6.

## Nuovi collegamenti

- `B36`: r3 ↔ r6 — IPv4 `10.0.11.0/30`, IPv6 `2001:db8:36::/64`
- `B56`: r5 ↔ r6 — IPv4 `10.0.12.0/30`, IPv6 `2001:db8:56::/64`
- `B67`: r6 ↔ r7 — IPv4 `10.0.13.0/30`, IPv6 `2001:db8:67::/64`
- `B47`: r4 ↔ r7 — IPv4 `10.0.14.0/30`, IPv6 `2001:db8:47::/64`

## Nuove LAN

| LAN | Router | PC IPv4 | PC IPv6 |
|---|---|---|---|
| A6 | r6 `200.0.11.1`, `2001:db8:6::1` | pc11 `200.0.11.2` | pc13 `2001:db8:6::13` |
| A7 | r7 `100.0.12.1`, `2001:db8:7::1` | pc12 `100.0.12.2` | pc14 `2001:db8:7::14` |

Ogni router contiene rotte statiche verso **tutte le reti IPv4 e IPv6 non direttamente connesse**. I PC usano il router della propria LAN come gateway predefinito.

Avvio rapido:

```sh
kathara lstart --noterminals
kathara linfo
kathara exec pc11 -- ping -c 2 100.0.12.2
kathara exec pc13 -- ping -6 -c 2 2001:db8:7::14
kathara exec r6 -- ip route show
kathara exec r6 -- ip -6 route show
kathara lclean
```
