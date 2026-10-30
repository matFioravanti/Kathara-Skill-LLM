$TTL 3600
@ IN SOA ns.service.com. hostmaster.service.com. ( 1 3600 900 604800 300 )
@ IN NS ns.service.com.
ns IN A 10.14.2.11
@ IN MX 10 mail.service.com.
mail IN A 10.14.2.11
api IN NS ns.api.service.com.
ns.api IN A 10.14.3.12
