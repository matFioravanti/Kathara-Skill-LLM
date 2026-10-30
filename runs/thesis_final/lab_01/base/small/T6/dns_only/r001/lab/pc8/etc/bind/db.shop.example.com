$ORIGIN shop.example.com.
$TTL 3600
@ IN SOA ns.shop.example.com. hostmaster.shop.example.com. ( 1 3600 900 604800 300 )
@ IN NS ns.shop.example.com.
ns.shop.example.com. IN A 10.14.3.11
@ IN A 10.14.3.11
