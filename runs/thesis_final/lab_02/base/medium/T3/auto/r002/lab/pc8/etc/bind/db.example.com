$TTL 3600
$ORIGIN example.com.
@ IN SOA ns.example.com. hostmaster.example.com. ( 1 3600 900 604800 300 )
@ IN NS ns.example.com.
ns.example.com. IN A 10.15.2.14
shop IN A 10.15.4.14
blog IN A 10.15.5.11
