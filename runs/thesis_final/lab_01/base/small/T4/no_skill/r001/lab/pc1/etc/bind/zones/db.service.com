$TTL 3600
@ IN SOA ns.service.com. hostmaster.service.com. ( 1 3600 600 604800 3600 )
  IN NS ns.service.com.
  IN MX 10 mail.service.com.
ns IN A 10.14.1.11
mail IN A 10.14.2.11
api IN A 10.14.3.12
