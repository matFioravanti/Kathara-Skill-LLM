$TTL 3600
@ IN SOA ns.com. hostmaster.com. ( 1 3600 900 604800 300 )
@ IN NS ns.com.
ns IN A 10.15.1.13
shop.example.com. IN A 10.15.4.14
blog.example.com. IN A 10.15.5.11
dept.company.com. IN A 10.15.5.12
intranet.company.com. IN A 10.15.5.13
api.service.com. IN A 10.15.5.14
mail.company.com. IN A 10.15.2.13
company.com. IN MX 10 mail.company.com.
