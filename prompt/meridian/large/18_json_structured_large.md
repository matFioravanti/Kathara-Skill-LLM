{
  "task": "modify_existing_kathara_lab",
  "service": "dns",
  "description": "Configure the DNS hierarchy of the large laboratory according to the specified zones, delegations, and records.",
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
      ".": "[pc38]",
      "digital": "[pc17]",
      "network": "[pc35]",
      "science": "[pc1]",
      "region": "[pc2]",
      "meridian.digital": "[pc10]",
      "vantage.digital": "[pc48]",
      "vertex.digital": "[pc5]",
      "cipher.network": "[pc40]",
      "gateway.network": "[pc33]",
      "oakridge.science": "[pc37]",
      "lighthouse.science": "[pc7]",
      "solstice.region": "[pc28]",
      "meadow.region": "[pc30]",
      "valley.region": "[pc25]",
      "market.meridian.digital": "[pc22]",
      "journal.meridian.digital": "[pc23]",
      "teams.vantage.digital": "[pc29]",
      "office.vantage.digital": "[pc43]",
      "interface.vertex.digital": "[pc6]",
      "testing.cipher.network": "[pc24]",
      "neural.testing.cipher.network": "[pc47]",
      "records.testing.cipher.network": "[pc27]",
      "staging.cipher.network": "[pc4]",
      "pipeline.gateway.network": "[pc3]",
      "tunnel.oakridge.science": "[pc44]",
      "classes.oakridge.science": "[pc11]",
      "dashboard.lighthouse.science": "[pc46]",
      "learners.solstice.region": "[pc45]",
      "forms.meadow.region": "[pc8]",
      "metrics.valley.region": "[pc39]",
      "foundation": "[pc16]",
      "platform": "[pc20]",
      "public": "[pc31]",
      "press": "[pc34]",
      "bridge.foundation": "[pc49]",
      "horizon.foundation": "[pc36]",
      "sprout.platform": "[pc13]",
      "helix.platform": "[pc9]",
      "central.public": "[pc21]",
      "bulletin.press": "[pc18]",
      "collections.bridge.foundation": "[pc41]",
      "guides.horizon.foundation": "[pc19]",
      "functions.sprout.platform": "[pc26]",
      "uptime.helix.platform": "[pc32]",
      "opendata.central.public": "[pc42]",
      "support.central.public": "[pc14]",
      "district.bulletin.press": "[pc15]",
      "broadcast.bulletin.press": "[pc12]"
    },
    "delegations": {
      ".": [
        "digital",
        "network",
        "science",
        "region",
        "foundation",
        "platform",
        "public",
        "press"
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
      ],
      "foundation": [
        "bridge.foundation",
        "horizon.foundation"
      ],
      "platform": [
        "sprout.platform",
        "helix.platform"
      ],
      "public": [
        "central.public"
      ],
      "press": [
        "bulletin.press"
      ],
      "bridge.foundation": [
        "collections.bridge.foundation"
      ],
      "horizon.foundation": [
        "guides.horizon.foundation"
      ],
      "sprout.platform": [
        "functions.sprout.platform"
      ],
      "helix.platform": [
        "uptime.helix.platform"
      ],
      "central.public": [
        "opendata.central.public",
        "support.central.public"
      ],
      "bulletin.press": [
        "district.bulletin.press",
        "broadcast.bulletin.press"
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
    "root_hints": "existing_root_server_[pc38]",
    "clients": "all_existing_client_hosts"
  },
  "zone_records": {
    "A": {
      "market.meridian.digital": "existing_ipv4_of_pc22",
      "journal.meridian.digital": "existing_ipv4_of_pc23",
      "teams.vantage.digital": "existing_ipv4_of_pc29",
      "office.vantage.digital": "existing_ipv4_of_pc43",
      "interface.vertex.digital": "existing_ipv4_of_pc6",
      "neural.testing.cipher.network": "existing_ipv4_of_pc47",
      "records.testing.cipher.network": "existing_ipv4_of_pc27",
      "staging.cipher.network": "existing_ipv4_of_pc4",
      "pipeline.gateway.network": "existing_ipv4_of_pc3",
      "tunnel.oakridge.science": "existing_ipv4_of_pc44",
      "classes.oakridge.science": "existing_ipv4_of_pc11",
      "dashboard.lighthouse.science": "existing_ipv4_of_pc46",
      "learners.solstice.region": "existing_ipv4_of_pc45",
      "forms.meadow.region": "existing_ipv4_of_pc8",
      "metrics.valley.region": "existing_ipv4_of_pc39",
      "collections.bridge.foundation": "existing_ipv4_of_pc41",
      "guides.horizon.foundation": "existing_ipv4_of_pc19",
      "functions.sprout.platform": "existing_ipv4_of_pc26",
      "uptime.helix.platform": "existing_ipv4_of_pc32",
      "opendata.central.public": "existing_ipv4_of_pc42",
      "support.central.public": "existing_ipv4_of_pc14",
      "district.bulletin.press": "existing_ipv4_of_pc15",
      "broadcast.bulletin.press": "existing_ipv4_of_pc12",
      "mailhub.vantage.digital": "existing_ipv4_of_pc48",
      "mailhub.oakridge.science": "existing_ipv4_of_pc37",
      "mailhub.teams.vantage.digital": "existing_ipv4_of_pc29",
      "mailhub.support.central.public": "existing_ipv4_of_pc14"
    },
    "MX": {
      "vantage.digital": {
        "preference": 10,
        "exchange": "mailhub.vantage.digital"
      },
      "oakridge.science": {
        "preference": 10,
        "exchange": "mailhub.oakridge.science"
      },
      "teams.vantage.digital": {
        "preference": 10,
        "exchange": "mailhub.teams.vantage.digital"
      },
      "support.central.public": {
        "preference": 10,
        "exchange": "mailhub.support.central.public"
      }
    }
  }
}
