$TTL 3600
@ IN SOA ns.example.com. hostmaster.example.com. ( 1 3600 900 604800 300 )
@ IN NS ns.example.com.
ns IN A 10.14.1.14
www IN A 10.14.1.14
@ IN MX 10 mail.example.com.
mail IN A 10.14.1.14
shop IN NS ns.shop.example.com.
ns.shop IN A 10.14.3.11
