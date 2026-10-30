$TTL 3600
@ IN SOA ns.example.com. hostmaster.example.com. ( 1 3600 600 604800 3600 )
  IN NS ns.example.com.
  IN MX 10 mail.example.com.
ns IN A 10.14.1.11
mail IN A 10.14.1.14
shop IN A 10.14.3.11
