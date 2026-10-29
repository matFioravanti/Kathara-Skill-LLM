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
      ".": "[pc3]",
      "tech": "[pc31]",
      "cloud": "[pc17]",
      "academy": "[pc24]",
      "city": "[pc12]",
      "nimbus.tech": "[pc10]",
      "orbit.tech": "[pc6]",
      "forge.tech": "[pc26]",
      "quantum.cloud": "[pc5]",
      "matrix.cloud": "[pc2]",
      "summit.academy": "[pc29]",
      "cedar.academy": "[pc13]",
      "polaris.city": "[pc4]",
      "riverton.city": "[pc22]",
      "highland.city": "[pc30]",
      "store.nimbus.tech": "[pc25]",
      "insights.nimbus.tech": "[pc23]",
      "division.orbit.tech": "[pc7]",
      "internal.orbit.tech": "[pc1]",
      "gateway.forge.tech": "[pc28]",
      "experiments.quantum.cloud": "[pc15]",
      "models.experiments.quantum.cloud": "[pc20]",
      "datasets.experiments.quantum.cloud": "[pc18]",
      "sandbox.quantum.cloud": "[pc14]",
      "build.matrix.cloud": "[pc8]",
      "secure.summit.academy": "[pc11]",
      "lessons.summit.academy": "[pc9]",
      "entry.cedar.academy": "[pc21]",
      "students.polaris.city": "[pc19]",
      "requests.riverton.city": "[pc16]",
      "statistics.highland.city": "[pc27]"
    },
    "delegations": {
      ".": [
        "tech",
        "cloud",
        "academy",
        "city"
      ],
      "tech": [
        "nimbus.tech",
        "orbit.tech",
        "forge.tech"
      ],
      "cloud": [
        "quantum.cloud",
        "matrix.cloud"
      ],
      "academy": [
        "summit.academy",
        "cedar.academy"
      ],
      "city": [
        "polaris.city",
        "riverton.city",
        "highland.city"
      ],
      "nimbus.tech": [
        "store.nimbus.tech",
        "insights.nimbus.tech"
      ],
      "orbit.tech": [
        "division.orbit.tech",
        "internal.orbit.tech"
      ],
      "forge.tech": [
        "gateway.forge.tech"
      ],
      "quantum.cloud": [
        "experiments.quantum.cloud",
        "sandbox.quantum.cloud"
      ],
      "matrix.cloud": [
        "build.matrix.cloud"
      ],
      "experiments.quantum.cloud": [
        "models.experiments.quantum.cloud",
        "datasets.experiments.quantum.cloud"
      ],
      "summit.academy": [
        "secure.summit.academy",
        "lessons.summit.academy"
      ],
      "cedar.academy": [
        "entry.cedar.academy"
      ],
      "polaris.city": [
        "students.polaris.city"
      ],
      "riverton.city": [
        "requests.riverton.city"
      ],
      "highland.city": [
        "statistics.highland.city"
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
    "root_hints": "existing_root_server_[pc3]",
    "clients": "all_existing_client_hosts"
  },
  "zone_records": {
    "A": {
      "store.nimbus.tech": "existing_ipv4_of_pc25",
      "insights.nimbus.tech": "existing_ipv4_of_pc23",
      "division.orbit.tech": "existing_ipv4_of_pc7",
      "internal.orbit.tech": "existing_ipv4_of_pc1",
      "gateway.forge.tech": "existing_ipv4_of_pc28",
      "models.experiments.quantum.cloud": "existing_ipv4_of_pc20",
      "datasets.experiments.quantum.cloud": "existing_ipv4_of_pc18",
      "sandbox.quantum.cloud": "existing_ipv4_of_pc14",
      "build.matrix.cloud": "existing_ipv4_of_pc8",
      "secure.summit.academy": "existing_ipv4_of_pc11",
      "lessons.summit.academy": "existing_ipv4_of_pc9",
      "entry.cedar.academy": "existing_ipv4_of_pc21",
      "students.polaris.city": "existing_ipv4_of_pc19",
      "requests.riverton.city": "existing_ipv4_of_pc16",
      "statistics.highland.city": "existing_ipv4_of_pc27",
      "web.nimbus.tech": "existing_ipv4_of_web_service_host",
      "mx.orbit.tech": "existing_ipv4_of_pc6",
      "mx.summit.academy": "existing_ipv4_of_pc29"
    },
    "MX": {
      "orbit.tech": {
        "preference": 10,
        "exchange": "mx.orbit.tech"
      },
      "summit.academy": {
        "preference": 10,
        "exchange": "mx.summit.academy"
      }
    }
  }
}
