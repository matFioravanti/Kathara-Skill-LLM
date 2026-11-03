$TTL 3600
$ORIGIN service.com.
@ IN SOA ns.service.com. hostmaster.service.com. ( 1 3600 900 604800 300 )
@ IN NS ns.service.com.
ns.service.com. IN A 10.15.3.12
api IN A 10.15.5.14
