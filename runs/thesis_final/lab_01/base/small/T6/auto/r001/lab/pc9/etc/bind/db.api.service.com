$TTL 3600
$ORIGIN api.service.com.
@ IN SOA ns.api.service.com. hostmaster.api.service.com. ( 1 3600 900 604800 300 )
@ IN NS ns.api.service.com.
ns.api.service.com. IN A 10.14.3.12
@ IN A 10.14.3.12
