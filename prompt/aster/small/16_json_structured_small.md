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
      ".": "[pc16]",
      "innovation": "[pc8]",
      "infrastructure": "[pc18]",
      "aster.innovation": "[pc15]",
      "vector.innovation": "[pc7]",
      "cascade.infrastructure": "[pc5]",
      "compass.infrastructure": "[pc20]",
      "catalog.aster.innovation": "[pc12]",
      "integration.vector.innovation": "[pc11]",
      "studies.cascade.infrastructure": "[pc9]",
      "automation.compass.infrastructure": "[pc3]",
      "agents.studies.cascade.infrastructure": "[pc13]",
      "warehouse.studies.cascade.infrastructure": "[pc19]"
    },
    "delegations": {
      ".": [
        "innovation",
        "infrastructure"
      ],
      "innovation": [
        "aster.innovation",
        "vector.innovation"
      ],
      "infrastructure": [
        "cascade.infrastructure",
        "compass.infrastructure"
      ],
      "aster.innovation": [
        "catalog.aster.innovation"
      ],
      "vector.innovation": [
        "integration.vector.innovation"
      ],
      "cascade.infrastructure": [
        "studies.cascade.infrastructure"
      ],
      "compass.infrastructure": [
        "automation.compass.infrastructure"
      ],
      "studies.cascade.infrastructure": [
        "agents.studies.cascade.infrastructure",
        "warehouse.studies.cascade.infrastructure"
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
    "local_nameserver": "[pc17]",
    "recursive_resolution": true,
    "root_hints": "existing_root_server_[pc16]",
    "clients": [
      "[pc1]",
      "[pc6]",
      "[pc4]",
      "[pc10]",
      "[pc14]"
    ]
  },
  "zone_records": {
    "A": {
      "catalog.aster.innovation": "existing_ipv4_of_pc12",
      "integration.vector.innovation": "existing_ipv4_of_pc11",
      "automation.compass.infrastructure": "existing_ipv4_of_pc3",
      "agents.studies.cascade.infrastructure": "existing_ipv4_of_pc13",
      "warehouse.studies.cascade.infrastructure": "existing_ipv4_of_pc19",
      "portalweb.aster.innovation": "existing_ipv4_of_web_service_host",
      "inbox.aster.innovation": "existing_ipv4_of_pc15",
      "inbox.vector.innovation": "existing_ipv4_of_pc7",
      "inbox.cascade.infrastructure": "existing_ipv4_of_pc5",
      "inbox.compass.infrastructure": "existing_ipv4_of_pc20"
    },
    "MX": {
      "aster.innovation": {
        "preference": 10,
        "exchange": "inbox.aster.innovation"
      },
      "vector.innovation": {
        "preference": 10,
        "exchange": "inbox.vector.innovation"
      },
      "cascade.infrastructure": {
        "preference": 10,
        "exchange": "inbox.cascade.infrastructure"
      },
      "compass.infrastructure": {
        "preference": 10,
        "exchange": "inbox.compass.infrastructure"
      }
    }
  }
}
