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
      ".": "[pc37]",
      "innovation": "[pc3]",
      "infrastructure": "[pc15]",
      "learning": "[pc29]",
      "territory": "[pc28]",
      "aster.innovation": "[pc14]",
      "pinnacle.innovation": "[pc39]",
      "vector.innovation": "[pc6]",
      "cascade.infrastructure": "[pc1]",
      "compass.infrastructure": "[pc9]",
      "northstar.learning": "[pc22]",
      "equinox.learning": "[pc21]",
      "helios.territory": "[pc33]",
      "brookfield.territory": "[pc24]",
      "sierra.territory": "[pc7]",
      "catalog.aster.innovation": "[pc27]",
      "stories.aster.innovation": "[pc38]",
      "units.pinnacle.innovation": "[pc5]",
      "private.pinnacle.innovation": "[pc31]",
      "integration.vector.innovation": "[pc11]",
      "studies.cascade.infrastructure": "[pc43]",
      "agents.studies.cascade.infrastructure": "[pc42]",
      "warehouse.studies.cascade.infrastructure": "[pc30]",
      "prototype.cascade.infrastructure": "[pc41]",
      "automation.compass.infrastructure": "[pc36]",
      "remote.northstar.learning": "[pc16]",
      "lectures.northstar.learning": "[pc46]",
      "homepage.equinox.learning": "[pc45]",
      "scholars.helios.territory": "[pc48]",
      "assistance.brookfield.territory": "[pc26]",
      "indicators.sierra.territory": "[pc2]",
      "nonprofit": "[pc4]",
      "compute": "[pc35]",
      "services": "[pc17]",
      "journal": "[pc49]",
      "alliance.nonprofit": "[pc23]",
      "blueprint.nonprofit": "[pc32]",
      "ember.compute": "[pc12]",
      "krypton.compute": "[pc47]",
      "federal.services": "[pc19]",
      "chronicle.journal": "[pc40]",
      "history.alliance.nonprofit": "[pc34]",
      "references.blueprint.nonprofit": "[pc44]",
      "microservice.ember.compute": "[pc8]",
      "monitor.krypton.compute": "[pc20]",
      "disclosure.federal.services": "[pc10]",
      "serviceshub.federal.services": "[pc13]",
      "neighborhood.chronicle.journal": "[pc18]",
      "channels.chronicle.journal": "[pc25]"
    },
    "delegations": {
      ".": [
        "innovation",
        "infrastructure",
        "learning",
        "territory",
        "nonprofit",
        "compute",
        "services",
        "journal"
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
      ],
      "nonprofit": [
        "alliance.nonprofit",
        "blueprint.nonprofit"
      ],
      "compute": [
        "ember.compute",
        "krypton.compute"
      ],
      "services": [
        "federal.services"
      ],
      "journal": [
        "chronicle.journal"
      ],
      "alliance.nonprofit": [
        "history.alliance.nonprofit"
      ],
      "blueprint.nonprofit": [
        "references.blueprint.nonprofit"
      ],
      "ember.compute": [
        "microservice.ember.compute"
      ],
      "krypton.compute": [
        "monitor.krypton.compute"
      ],
      "federal.services": [
        "disclosure.federal.services",
        "serviceshub.federal.services"
      ],
      "chronicle.journal": [
        "neighborhood.chronicle.journal",
        "channels.chronicle.journal"
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
    "root_hints": "existing_root_server_[pc37]",
    "clients": "all_existing_client_hosts"
  },
  "zone_records": {
    "A": {
      "catalog.aster.innovation": "existing_ipv4_of_pc27",
      "stories.aster.innovation": "existing_ipv4_of_pc38",
      "units.pinnacle.innovation": "existing_ipv4_of_pc5",
      "private.pinnacle.innovation": "existing_ipv4_of_pc31",
      "integration.vector.innovation": "existing_ipv4_of_pc11",
      "agents.studies.cascade.infrastructure": "existing_ipv4_of_pc42",
      "warehouse.studies.cascade.infrastructure": "existing_ipv4_of_pc30",
      "prototype.cascade.infrastructure": "existing_ipv4_of_pc41",
      "automation.compass.infrastructure": "existing_ipv4_of_pc36",
      "remote.northstar.learning": "existing_ipv4_of_pc16",
      "lectures.northstar.learning": "existing_ipv4_of_pc46",
      "homepage.equinox.learning": "existing_ipv4_of_pc45",
      "scholars.helios.territory": "existing_ipv4_of_pc48",
      "assistance.brookfield.territory": "existing_ipv4_of_pc26",
      "indicators.sierra.territory": "existing_ipv4_of_pc2",
      "history.alliance.nonprofit": "existing_ipv4_of_pc34",
      "references.blueprint.nonprofit": "existing_ipv4_of_pc44",
      "microservice.ember.compute": "existing_ipv4_of_pc8",
      "monitor.krypton.compute": "existing_ipv4_of_pc20",
      "disclosure.federal.services": "existing_ipv4_of_pc10",
      "serviceshub.federal.services": "existing_ipv4_of_pc13",
      "neighborhood.chronicle.journal": "existing_ipv4_of_pc18",
      "channels.chronicle.journal": "existing_ipv4_of_pc25",
      "inbox.pinnacle.innovation": "existing_ipv4_of_pc39",
      "inbox.northstar.learning": "existing_ipv4_of_pc22",
      "inbox.units.pinnacle.innovation": "existing_ipv4_of_pc5",
      "inbox.serviceshub.federal.services": "existing_ipv4_of_pc13"
    },
    "MX": {
      "pinnacle.innovation": {
        "preference": 10,
        "exchange": "inbox.pinnacle.innovation"
      },
      "northstar.learning": {
        "preference": 10,
        "exchange": "inbox.northstar.learning"
      },
      "units.pinnacle.innovation": {
        "preference": 10,
        "exchange": "inbox.units.pinnacle.innovation"
      },
      "serviceshub.federal.services": {
        "preference": 10,
        "exchange": "inbox.serviceshub.federal.services"
      }
    }
  }
}
