{
  "task": "modify_existing_kathara_lab",
  "service": "dns",
  "description": "Configure the DNS hierarchy of the small laboratory according to the specified zones, delegations, and records.",
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
      "example.com": "[pc4]",
      "service.com": "[pc5]",
      "lab.net": "[pc6]",
      "tools.net": "[pc7]",
      "shop.example.com": "[pc8]",
      "api.service.com": "[pc9]",
      "research.lab.net": "[pc10]",
      "ci.tools.net": "[pc11]",
      "ai.research.lab.net": "[pc12]",
      "data.research.lab.net": "[pc13]"
    },
    "delegations": {
      ".": [
        "com",
        "net"
      ],
      "com": [
        "example.com",
        "service.com"
      ],
      "net": [
        "lab.net",
        "tools.net"
      ],
      "example.com": [
        "shop.example.com"
      ],
      "service.com": [
        "api.service.com"
      ],
      "lab.net": [
        "research.lab.net"
      ],
      "tools.net": [
        "ci.tools.net"
      ],
      "research.lab.net": [
        "ai.research.lab.net",
        "data.research.lab.net"
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
    "local_nameserver": "[pc14]",
    "recursive_resolution": true,
    "root_hints": "existing_root_server_[pc1]",
    "clients": [
      "[pc16]",
      "[pc17]",
      "[pc18]",
      "[pc19]",
      "[pc20]"
    ]
  },
  "zone_records": {
    "A": {
      "shop.example.com": "existing_ipv4_of_pc8",
      "api.service.com": "existing_ipv4_of_pc9",
      "ci.tools.net": "existing_ipv4_of_pc11",
      "ai.research.lab.net": "existing_ipv4_of_pc12",
      "data.research.lab.net": "existing_ipv4_of_pc13",
      "www.example.com": "existing_ipv4_of_web_service_host",
      "mail.example.com": "existing_ipv4_of_pc4",
      "mail.service.com": "existing_ipv4_of_pc5",
      "mail.lab.net": "existing_ipv4_of_pc6",
      "mail.tools.net": "existing_ipv4_of_pc7"
    },
    "MX": {
      "example.com": {
        "preference": 10,
        "exchange": "mail.example.com"
      },
      "service.com": {
        "preference": 10,
        "exchange": "mail.service.com"
      },
      "lab.net": {
        "preference": 10,
        "exchange": "mail.lab.net"
      },
      "tools.net": {
        "preference": 10,
        "exchange": "mail.tools.net"
      }
    }
  }
}
