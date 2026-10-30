$TTL 3600
@ IN SOA ns.com. hostmaster.com. ( 1 3600 900 604800 300 )
@ IN NS ns.com.
ns IN A 10.14.1.12
example IN NS ns.example.com.
ns.example IN A 10.14.3.13
service IN NS ns.service.com.
ns.service IN A 10.14.4.14
