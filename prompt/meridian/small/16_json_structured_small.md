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
      ".": "[pc17]",
      "digital": "[pc7]",
      "network": "[pc5]",
      "meridian.digital": "[pc14]",
      "vertex.digital": "[pc16]",
      "cipher.network": "[pc4]",
      "gateway.network": "[pc9]",
      "market.meridian.digital": "[pc10]",
      "interface.vertex.digital": "[pc2]",
      "testing.cipher.network": "[pc20]",
      "pipeline.gateway.network": "[pc15]",
      "neural.testing.cipher.network": "[pc18]",
      "records.testing.cipher.network": "[pc3]"
    },
    "delegations": {
      ".": [
        "digital",
        "network"
      ],
      "digital": [
        "meridian.digital",
        "vertex.digital"
      ],
      "network": [
        "cipher.network",
        "gateway.network"
      ],
      "meridian.digital": [
        "market.meridian.digital"
      ],
      "vertex.digital": [
        "interface.vertex.digital"
      ],
      "cipher.network": [
        "testing.cipher.network"
      ],
      "gateway.network": [
        "pipeline.gateway.network"
      ],
      "testing.cipher.network": [
        "neural.testing.cipher.network",
        "records.testing.cipher.network"
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
    "local_nameserver": "[pc8]",
    "recursive_resolution": true,
    "root_hints": "existing_root_server_[pc17]",
    "clients": [
      "[pc12]",
      "[pc19]",
      "[pc11]",
      "[pc1]",
      "[pc6]"
    ]
  },
  "zone_records": {
    "A": {
      "market.meridian.digital": "existing_ipv4_of_pc10",
      "interface.vertex.digital": "existing_ipv4_of_pc2",
      "pipeline.gateway.network": "existing_ipv4_of_pc15",
      "neural.testing.cipher.network": "existing_ipv4_of_pc18",
      "records.testing.cipher.network": "existing_ipv4_of_pc3",
      "site.meridian.digital": "existing_ipv4_of_web_service_host",
      "mailhub.meridian.digital": "existing_ipv4_of_pc14",
      "mailhub.vertex.digital": "existing_ipv4_of_pc16",
      "mailhub.cipher.network": "existing_ipv4_of_pc4",
      "mailhub.gateway.network": "existing_ipv4_of_pc9"
    },
    "MX": {
      "meridian.digital": {
        "preference": 10,
        "exchange": "mailhub.meridian.digital"
      },
      "vertex.digital": {
        "preference": 10,
        "exchange": "mailhub.vertex.digital"
      },
      "cipher.network": {
        "preference": 10,
        "exchange": "mailhub.cipher.network"
      },
      "gateway.network": {
        "preference": 10,
        "exchange": "mailhub.gateway.network"
      }
    }
  }
}
