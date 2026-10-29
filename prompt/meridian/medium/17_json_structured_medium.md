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
      ".": "[pc25]",
      "digital": "[pc14]",
      "network": "[pc20]",
      "science": "[pc6]",
      "region": "[pc15]",
      "meridian.digital": "[pc2]",
      "vantage.digital": "[pc22]",
      "vertex.digital": "[pc11]",
      "cipher.network": "[pc17]",
      "gateway.network": "[pc4]",
      "oakridge.science": "[pc24]",
      "lighthouse.science": "[pc5]",
      "solstice.region": "[pc21]",
      "meadow.region": "[pc18]",
      "valley.region": "[pc19]",
      "market.meridian.digital": "[pc13]",
      "journal.meridian.digital": "[pc26]",
      "teams.vantage.digital": "[pc23]",
      "office.vantage.digital": "[pc16]",
      "interface.vertex.digital": "[pc10]",
      "testing.cipher.network": "[pc30]",
      "neural.testing.cipher.network": "[pc9]",
      "records.testing.cipher.network": "[pc12]",
      "staging.cipher.network": "[pc28]",
      "pipeline.gateway.network": "[pc7]",
      "tunnel.oakridge.science": "[pc3]",
      "classes.oakridge.science": "[pc1]",
      "dashboard.lighthouse.science": "[pc29]",
      "learners.solstice.region": "[pc8]",
      "forms.meadow.region": "[pc31]",
      "metrics.valley.region": "[pc27]"
    },
    "delegations": {
      ".": [
        "digital",
        "network",
        "science",
        "region"
      ],
      "digital": [
        "meridian.digital",
        "vantage.digital",
        "vertex.digital"
      ],
      "network": [
        "cipher.network",
        "gateway.network"
      ],
      "science": [
        "oakridge.science",
        "lighthouse.science"
      ],
      "region": [
        "solstice.region",
        "meadow.region",
        "valley.region"
      ],
      "meridian.digital": [
        "market.meridian.digital",
        "journal.meridian.digital"
      ],
      "vantage.digital": [
        "teams.vantage.digital",
        "office.vantage.digital"
      ],
      "vertex.digital": [
        "interface.vertex.digital"
      ],
      "cipher.network": [
        "testing.cipher.network",
        "staging.cipher.network"
      ],
      "gateway.network": [
        "pipeline.gateway.network"
      ],
      "testing.cipher.network": [
        "neural.testing.cipher.network",
        "records.testing.cipher.network"
      ],
      "oakridge.science": [
        "tunnel.oakridge.science",
        "classes.oakridge.science"
      ],
      "lighthouse.science": [
        "dashboard.lighthouse.science"
      ],
      "solstice.region": [
        "learners.solstice.region"
      ],
      "meadow.region": [
        "forms.meadow.region"
      ],
      "valley.region": [
        "metrics.valley.region"
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
    "root_hints": "existing_root_server_[pc25]",
    "clients": "all_existing_client_hosts"
  },
  "zone_records": {
    "A": {
      "market.meridian.digital": "existing_ipv4_of_pc13",
      "journal.meridian.digital": "existing_ipv4_of_pc26",
      "teams.vantage.digital": "existing_ipv4_of_pc23",
      "office.vantage.digital": "existing_ipv4_of_pc16",
      "interface.vertex.digital": "existing_ipv4_of_pc10",
      "neural.testing.cipher.network": "existing_ipv4_of_pc9",
      "records.testing.cipher.network": "existing_ipv4_of_pc12",
      "staging.cipher.network": "existing_ipv4_of_pc28",
      "pipeline.gateway.network": "existing_ipv4_of_pc7",
      "tunnel.oakridge.science": "existing_ipv4_of_pc3",
      "classes.oakridge.science": "existing_ipv4_of_pc1",
      "dashboard.lighthouse.science": "existing_ipv4_of_pc29",
      "learners.solstice.region": "existing_ipv4_of_pc8",
      "forms.meadow.region": "existing_ipv4_of_pc31",
      "metrics.valley.region": "existing_ipv4_of_pc27",
      "site.meridian.digital": "existing_ipv4_of_web_service_host",
      "mailhub.vantage.digital": "existing_ipv4_of_pc22",
      "mailhub.oakridge.science": "existing_ipv4_of_pc24"
    },
    "MX": {
      "vantage.digital": {
        "preference": 10,
        "exchange": "mailhub.vantage.digital"
      },
      "oakridge.science": {
        "preference": 10,
        "exchange": "mailhub.oakridge.science"
      }
    }
  }
}
