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
      ".": "[pc8]",
      "tech": "[pc18]",
      "cloud": "[pc12]",
      "nimbus.tech": "[pc1]",
      "forge.tech": "[pc17]",
      "quantum.cloud": "[pc14]",
      "matrix.cloud": "[pc9]",
      "store.nimbus.tech": "[pc6]",
      "gateway.forge.tech": "[pc11]",
      "experiments.quantum.cloud": "[pc3]",
      "build.matrix.cloud": "[pc16]",
      "models.experiments.quantum.cloud": "[pc7]",
      "datasets.experiments.quantum.cloud": "[pc20]"
    },
    "delegations": {
      ".": [
        "tech",
        "cloud"
      ],
      "tech": [
        "nimbus.tech",
        "forge.tech"
      ],
      "cloud": [
        "quantum.cloud",
        "matrix.cloud"
      ],
      "nimbus.tech": [
        "store.nimbus.tech"
      ],
      "forge.tech": [
        "gateway.forge.tech"
      ],
      "quantum.cloud": [
        "experiments.quantum.cloud"
      ],
      "matrix.cloud": [
        "build.matrix.cloud"
      ],
      "experiments.quantum.cloud": [
        "models.experiments.quantum.cloud",
        "datasets.experiments.quantum.cloud"
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
    "local_nameserver": "[pc2]",
    "recursive_resolution": true,
    "root_hints": "existing_root_server_[pc8]",
    "clients": [
      "[pc19]",
      "[pc5]",
      "[pc10]",
      "[pc4]",
      "[pc15]"
    ]
  },
  "zone_records": {
    "A": {
      "store.nimbus.tech": "existing_ipv4_of_pc6",
      "gateway.forge.tech": "existing_ipv4_of_pc11",
      "build.matrix.cloud": "existing_ipv4_of_pc16",
      "models.experiments.quantum.cloud": "existing_ipv4_of_pc7",
      "datasets.experiments.quantum.cloud": "existing_ipv4_of_pc20",
      "web.nimbus.tech": "existing_ipv4_of_web_service_host",
      "mx.nimbus.tech": "existing_ipv4_of_pc1",
      "mx.forge.tech": "existing_ipv4_of_pc17",
      "mx.quantum.cloud": "existing_ipv4_of_pc14",
      "mx.matrix.cloud": "existing_ipv4_of_pc9"
    },
    "MX": {
      "nimbus.tech": {
        "preference": 10,
        "exchange": "mx.nimbus.tech"
      },
      "forge.tech": {
        "preference": 10,
        "exchange": "mx.forge.tech"
      },
      "quantum.cloud": {
        "preference": 10,
        "exchange": "mx.quantum.cloud"
      },
      "matrix.cloud": {
        "preference": 10,
        "exchange": "mx.matrix.cloud"
      }
    }
  }
}
