$TTL 300
@ IN SOA ns.example.com. hostmaster.example.com. ( 1 3600 600 604800 300 )
@ IN NS ns.example.com.
ns IN A 10.15.1.11
shop IN A 10.15.4.14
blog IN A 10.15.5.11
