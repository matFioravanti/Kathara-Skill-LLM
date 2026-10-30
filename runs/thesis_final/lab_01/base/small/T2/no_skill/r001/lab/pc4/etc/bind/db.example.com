$ORIGIN example.com.
$TTL 3600
@ IN SOA ns.example.com. hostmaster.example.com. ( 2026103001 3600 900 604800 3600 )
@ IN NS ns.example.com.
ns.example.com. IN A 10.14.1.14
@ IN A 10.14.1.14
@ IN MX 10 mail.example.com.
mail IN A 10.14.1.14
www IN A 10.14.1.14
shop.example.com. IN NS ns.shop.example.com.
ns.shop.example.com. IN A 10.14.3.11
