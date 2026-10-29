$TTL 3600
@ IN SOA ns.api.service.com. hostmaster.api.service.com. ( 2026102901 3600 900 604800 3600 )
  IN NS ns.api.service.com.
ns IN A 10.14.3.12
@ IN A 10.14.3.12
