# Lab IPv4/IPv6 con rotte statiche

Il lab conserva gli indirizzi e le rotte IPv4 esistenti e aggiunge connettività IPv6 tra le cinque LAN. Tutti i router inoltrano IPv6 usando esclusivamente rotte statiche; i PC IPv6 hanno un gateway predefinito configurato nello startup.

| LAN | Router IPv6 | PC IPv6 |
| --- | --- | --- |
| A1 `2001:db8:1::/64` | r1 `2001:db8:1::1` | pc7 `2001:db8:1::7` |
| A2 `2001:db8:2::/64` | r2 `2001:db8:2::1` | pc8 `2001:db8:2::8` |
| A3 `2001:db8:3::/64` | r3 `2001:db8:3::1` | pc3 `2001:db8:3::2`, pc6 `2001:db8:3::6` |
| A4 `2001:db8:4::/64` | r4 `2001:db8:4::1` | pc9 `2001:db8:4::9` |
| A5 `2001:db8:5::/64` | r5 `2001:db8:5::1` | pc10 `2001:db8:5::10` |

I collegamenti tra router usano le reti `2001:db8:12::/64`, `2001:db8:14::/64`, `2001:db8:23::/64`, `2001:db8:24::/64`, `2001:db8:25::/64`, `2001:db8:35::/64` e `2001:db8:45::/64`.

Avvio e verifica rapida:

```sh
kathara lstart --noterminals
kathara linfo
kathara exec pc7 -- ping -6 -c 2 2001:db8:5::10
kathara exec pc6 -- ping -6 -c 2 2001:db8:2::8
kathara exec r3 -- ip -6 route show
kathara lclean
```
