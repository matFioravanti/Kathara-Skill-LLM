$TTL 3600
@ IN SOA ns.com. hostmaster.com. ( 2026102901 3600 900 604800 3600 )
  IN NS ns.com.
ns IN A 10.14.1.12
example IN NS ns.example.com.
ns.example IN A 10.14.1.14
service IN NS ns.service.com.
ns.service IN A 10.14.2.11
