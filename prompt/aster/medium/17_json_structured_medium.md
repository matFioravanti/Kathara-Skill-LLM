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
      ".": "[pc27]",
      "innovation": "[pc25]",
      "infrastructure": "[pc10]",
      "learning": "[pc2]",
      "territory": "[pc9]",
      "aster.innovation": "[pc23]",
      "pinnacle.innovation": "[pc30]",
      "vector.innovation": "[pc6]",
      "cascade.infrastructure": "[pc5]",
      "compass.infrastructure": "[pc14]",
      "northstar.learning": "[pc26]",
      "equinox.learning": "[pc17]",
      "helios.territory": "[pc20]",
      "brookfield.territory": "[pc12]",
      "sierra.territory": "[pc22]",
      "catalog.aster.innovation": "[pc31]",
      "stories.aster.innovation": "[pc8]",
      "units.pinnacle.innovation": "[pc4]",
      "private.pinnacle.innovation": "[pc28]",
      "integration.vector.innovation": "[pc15]",
      "studies.cascade.infrastructure": "[pc16]",
      "agents.studies.cascade.infrastructure": "[pc11]",
      "warehouse.studies.cascade.infrastructure": "[pc29]",
      "prototype.cascade.infrastructure": "[pc21]",
      "automation.compass.infrastructure": "[pc1]",
      "remote.northstar.learning": "[pc18]",
      "lectures.northstar.learning": "[pc3]",
      "homepage.equinox.learning": "[pc24]",
      "scholars.helios.territory": "[pc7]",
      "assistance.brookfield.territory": "[pc13]",
      "indicators.sierra.territory": "[pc19]"
    },
    "delegations": {
      ".": [
        "innovation",
        "infrastructure",
        "learning",
        "territory"
      ],
      "innovation": [
        "aster.innovation",
        "pinnacle.innovation",
        "vector.innovation"
      ],
      "infrastructure": [
        "cascade.infrastructure",
        "compass.infrastructure"
      ],
      "learning": [
        "northstar.learning",
        "equinox.learning"
      ],
      "territory": [
        "helios.territory",
        "brookfield.territory",
        "sierra.territory"
      ],
      "aster.innovation": [
        "catalog.aster.innovation",
        "stories.aster.innovation"
      ],
      "pinnacle.innovation": [
        "units.pinnacle.innovation",
        "private.pinnacle.innovation"
      ],
      "vector.innovation": [
        "integration.vector.innovation"
      ],
      "cascade.infrastructure": [
        "studies.cascade.infrastructure",
        "prototype.cascade.infrastructure"
      ],
      "compass.infrastructure": [
        "automation.compass.infrastructure"
      ],
      "studies.cascade.infrastructure": [
        "agents.studies.cascade.infrastructure",
        "warehouse.studies.cascade.infrastructure"
      ],
      "northstar.learning": [
        "remote.northstar.learning",
        "lectures.northstar.learning"
      ],
      "equinox.learning": [
        "homepage.equinox.learning"
      ],
      "helios.territory": [
        "scholars.helios.territory"
      ],
      "brookfield.territory": [
        "assistance.brookfield.territory"
      ],
      "sierra.territory": [
        "indicators.sierra.territory"
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
    "root_hints": "existing_root_server_[pc27]",
    "clients": "all_existing_client_hosts"
  },
  "zone_records": {
    "A": {
      "catalog.aster.innovation": "existing_ipv4_of_pc31",
      "stories.aster.innovation": "existing_ipv4_of_pc8",
      "units.pinnacle.innovation": "existing_ipv4_of_pc4",
      "private.pinnacle.innovation": "existing_ipv4_of_pc28",
      "integration.vector.innovation": "existing_ipv4_of_pc15",
      "agents.studies.cascade.infrastructure": "existing_ipv4_of_pc11",
      "warehouse.studies.cascade.infrastructure": "existing_ipv4_of_pc29",
      "prototype.cascade.infrastructure": "existing_ipv4_of_pc21",
      "automation.compass.infrastructure": "existing_ipv4_of_pc1",
      "remote.northstar.learning": "existing_ipv4_of_pc18",
      "lectures.northstar.learning": "existing_ipv4_of_pc3",
      "homepage.equinox.learning": "existing_ipv4_of_pc24",
      "scholars.helios.territory": "existing_ipv4_of_pc7",
      "assistance.brookfield.territory": "existing_ipv4_of_pc13",
      "indicators.sierra.territory": "existing_ipv4_of_pc19",
      "portalweb.aster.innovation": "existing_ipv4_of_web_service_host",
      "inbox.pinnacle.innovation": "existing_ipv4_of_pc30",
      "inbox.northstar.learning": "existing_ipv4_of_pc26"
    },
    "MX": {
      "pinnacle.innovation": {
        "preference": 10,
        "exchange": "inbox.pinnacle.innovation"
      },
      "northstar.learning": {
        "preference": 10,
        "exchange": "inbox.northstar.learning"
      }
    }
  }
}
