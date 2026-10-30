$TTL 3600
$ORIGIN service.com.
@ IN SOA ns.service.com. hostmaster.service.com. ( 1 3600 900 604800 300 )
@ IN NS ns.service.com.
ns.service.com. IN A 10.14.2.11
api.service.com. IN NS ns.api.service.com.
ns.api.service.com. IN A 10.14.3.12
mail IN A 10.14.2.11
@ IN MX 10 mail.service.com.
