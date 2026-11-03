$TTL 3600
@ IN SOA ns.com. hostmaster.com. ( 1 3600 900 604800 300 )
@ IN NS ns.com.
@ IN A 10.16.1.12
ns IN A 10.16.1.12
example IN NS ns.example.com.
ns.example.com. IN A 10.16.2.12
company IN NS ns.company.com.
ns.company.com. IN A 10.16.2.13
service IN NS ns.service.com.
ns.service.com. IN A 10.16.2.14
