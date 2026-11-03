$TTL 3600
@ IN SOA ns.service.com. hostmaster.service.com. ( 2026110301 3600 900 604800 3600 )
@ IN NS ns.service.com.
ns IN A 10.16.1.11
api.service.com. IN A 10.16.5.14
