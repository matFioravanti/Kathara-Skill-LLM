{
  "task": "modify_existing_kathara_lab",
  "service": "dns",
  "description": "Configure the DNS hierarchy of the medium-sized laboratory according to the specified zones, delegations, and records.",
  "constraints": {
    "preserve_existing_topology": true,
    "preserve_existing_ip_addresses": true,
    "preserve_existing_routes": true,
    "do_not_add_devices": true,
    "do_not_add_interfaces": true,
    "do_not_add_collision_domains": true,
    "use_existing_lab_addresses_only": true
  },
  "dns_hierarchy": {
    "root_zone": ".",
    "authoritative_zones": {
      ".": "[pc1]",
      "com": "[pc2]",
      "net": "[pc3]",
      "edu": "[pc4]",
      "it": "[pc5]",
      "example.com": "[pc6]",
      "company.com": "[pc7]",
      "service.com": "[pc8]",
      "lab.net": "[pc9]",
      "tools.net": "[pc10]",
      "university.edu": "[pc11]",
      "campus.edu": "[pc12]",
      "unibo.it": "[pc13]",
      "comune.it": "[pc14]",
      "regione.it": "[pc15]",
      "shop.example.com": "[pc16]",
      "blog.example.com": "[pc17]",
      "dept.company.com": "[pc18]",
      "intranet.company.com": "[pc19]",
      "api.service.com": "[pc20]",
      "research.lab.net": "[pc21]",
      "ai.research.lab.net": "[pc22]",
      "data.research.lab.net": "[pc23]",
      "dev.lab.net": "[pc24]",
      "ci.tools.net": "[pc25]",
      "vpn.university.edu": "[pc26]",
      "courses.university.edu": "[pc27]",
      "portal.campus.edu": "[pc28]",
      "studenti.unibo.it": "[pc29]",
      "servizi.comune.it": "[pc30]",
      "dati.regione.it": "[pc31]"
    },
    "delegations": {
      ".": [
        "com",
        "net",
        "edu",
        "it"
      ],
      "com": [
        "example.com",
        "company.com",
        "service.com"
      ],
      "net": [
        "lab.net",
        "tools.net"
      ],
      "edu": [
        "university.edu",
        "campus.edu"
      ],
      "it": [
        "unibo.it",
        "comune.it",
        "regione.it"
      ],
      "example.com": [
        "shop.example.com",
        "blog.example.com"
      ],
      "company.com": [
        "dept.company.com",
        "intranet.company.com"
      ],
      "service.com": [
        "api.service.com"
      ],
      "lab.net": [
        "research.lab.net",
        "dev.lab.net"
      ],
      "tools.net": [
        "ci.tools.net"
      ],
      "research.lab.net": [
        "ai.research.lab.net",
        "data.research.lab.net"
      ],
      "university.edu": [
        "vpn.university.edu",
        "courses.university.edu"
      ],
      "campus.edu": [
        "portal.campus.edu"
      ],
      "unibo.it": [
        "studenti.unibo.it"
      ],
      "comune.it": [
        "servizi.comune.it"
      ],
      "regione.it": [
        "dati.regione.it"
      ]
    },
    "zone_requirements": {
      "apex_records": [
        "SOA",
        "NS"
      ],
      "delegation_records": [
        "NS",
        "glue_if_needed"
      ],
      "authoritative_recursion": false
    }
  },
  "resolver_configuration": {
    "local_nameserver": "select_existing_non_authoritative_host",
    "recursive_resolution": true,
    "root_hints": "existing_root_server_[pc1]",
    "clients": "all_existing_client_hosts"
  },
  "zone_records": {
    "A": {
      "shop.example.com": "existing_ipv4_of_pc16",
      "blog.example.com": "existing_ipv4_of_pc17",
      "dept.company.com": "existing_ipv4_of_pc18",
      "intranet.company.com": "existing_ipv4_of_pc19",
      "api.service.com": "existing_ipv4_of_pc20",
      "ai.research.lab.net": "existing_ipv4_of_pc22",
      "data.research.lab.net": "existing_ipv4_of_pc23",
      "dev.lab.net": "existing_ipv4_of_pc24",
      "ci.tools.net": "existing_ipv4_of_pc25",
      "vpn.university.edu": "existing_ipv4_of_pc26",
      "courses.university.edu": "existing_ipv4_of_pc27",
      "portal.campus.edu": "existing_ipv4_of_pc28",
      "studenti.unibo.it": "existing_ipv4_of_pc29",
      "servizi.comune.it": "existing_ipv4_of_pc30",
      "dati.regione.it": "existing_ipv4_of_pc31",
      "www.example.com": "existing_ipv4_of_web_service_host",
      "mail.company.com": "existing_ipv4_of_pc7",
      "mail.university.edu": "existing_ipv4_of_pc11"
    },
    "MX": {
      "company.com": {
        "preference": 10,
        "exchange": "mail.company.com"
      },
      "university.edu": {
        "preference": 10,
        "exchange": "mail.university.edu"
      }
    }
  }
}
