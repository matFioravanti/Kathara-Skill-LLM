$TTL 300
@ IN SOA ns.service.com. hostmaster.service.com. ( 1 3600 600 604800 300 )
@ IN NS ns.service.com.
ns IN A 10.15.1.11
api IN A 10.15.5.14
