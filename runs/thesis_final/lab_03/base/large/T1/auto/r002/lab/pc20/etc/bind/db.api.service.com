$TTL 3600
@ IN SOA ns.api.service.com. hostmaster.api.service.com. ( 1 3600 900 604800 300 )
@ IN NS ns.api.service.com.
@ IN A 10.16.5.14
ns.api.service.com. IN A 10.16.5.14
