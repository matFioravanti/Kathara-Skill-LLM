$TTL 3600
@ IN SOA ns.service.com. hostmaster.service.com. ( 2026102901 3600 900 604800 3600 )
  IN NS ns.service.com.
ns IN A 10.14.2.11
mail IN A 10.14.2.11
@ IN MX 10 mail.service.com.
api IN NS ns.api.service.com.
ns.api IN A 10.14.3.12
