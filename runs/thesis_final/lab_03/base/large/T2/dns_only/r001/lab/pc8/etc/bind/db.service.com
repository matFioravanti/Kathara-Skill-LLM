$TTL 3600
@ IN SOA ns.service.com. hostmaster.service.com. ( 1 3600 900 604800 300 )
@ IN NS ns.service.com.
ns.service.com. IN A 10.16.2.14
@ IN A 10.16.2.14
api IN NS ns.api.service.com.
ns.api.service.com. IN A 10.16.5.14
