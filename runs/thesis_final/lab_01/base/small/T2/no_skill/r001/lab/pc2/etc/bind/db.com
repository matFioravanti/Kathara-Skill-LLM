$ORIGIN com.
$TTL 3600
@ IN SOA ns.com. hostmaster.com. ( 2026103001 3600 900 604800 3600 )
@ IN NS ns.com.
ns.com. IN A 10.14.1.12
example.com. IN NS ns.example.com.
ns.example.com. IN A 10.14.1.14
service.com. IN NS ns.service.com.
ns.service.com. IN A 10.14.2.11
