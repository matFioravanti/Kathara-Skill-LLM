$TTL 3600
$ORIGIN com.
@ IN SOA ns.com. hostmaster.com. ( 1 3600 900 604800 300 )
@ IN NS ns.com.
ns.com. IN A 10.15.1.13
example.com. IN NS ns.example.com.
ns.example.com. IN A 10.15.2.14
company.com. IN NS ns.company.com.
ns.company.com. IN A 10.15.3.11
service.com. IN NS ns.service.com.
ns.service.com. IN A 10.15.3.12
