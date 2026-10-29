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
      ".": "[pc13]",
      "tech": "[pc49]",
      "cloud": "[pc7]",
      "academy": "[pc29]",
      "city": "[pc48]",
      "nimbus.tech": "[pc20]",
      "orbit.tech": "[pc40]",
      "forge.tech": "[pc39]",
      "quantum.cloud": "[pc2]",
      "matrix.cloud": "[pc3]",
      "summit.academy": "[pc4]",
      "cedar.academy": "[pc1]",
      "polaris.city": "[pc16]",
      "riverton.city": "[pc19]",
      "highland.city": "[pc34]",
      "store.nimbus.tech": "[pc8]",
      "insights.nimbus.tech": "[pc38]",
      "division.orbit.tech": "[pc24]",
      "internal.orbit.tech": "[pc18]",
      "gateway.forge.tech": "[pc22]",
      "experiments.quantum.cloud": "[pc43]",
      "models.experiments.quantum.cloud": "[pc6]",
      "datasets.experiments.quantum.cloud": "[pc9]",
      "sandbox.quantum.cloud": "[pc47]",
      "build.matrix.cloud": "[pc15]",
      "secure.summit.academy": "[pc23]",
      "lessons.summit.academy": "[pc41]",
      "entry.cedar.academy": "[pc33]",
      "students.polaris.city": "[pc10]",
      "requests.riverton.city": "[pc12]",
      "statistics.highland.city": "[pc5]",
      "community": "[pc37]",
      "systems": "[pc31]",
      "agency": "[pc44]",
      "media": "[pc42]",
      "harbor.community": "[pc11]",
      "keystone.community": "[pc14]",
      "nova.systems": "[pc27]",
      "stratus.systems": "[pc36]",
      "civic.agency": "[pc45]",
      "pulse.media": "[pc21]",
      "vault.harbor.community": "[pc30]",
      "manuals.keystone.community": "[pc28]",
      "endpoint.nova.systems": "[pc46]",
      "health.stratus.systems": "[pc32]",
      "transparency.civic.agency": "[pc17]",
      "citizens.civic.agency": "[pc26]",
      "localdesk.pulse.media": "[pc35]",
      "streams.pulse.media": "[pc25]"
    },
    "delegations": {
      ".": [
        "tech",
        "cloud",
        "academy",
        "city",
        "community",
        "systems",
        "agency",
        "media"
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
      ],
      "community": [
        "harbor.community",
        "keystone.community"
      ],
      "systems": [
        "nova.systems",
        "stratus.systems"
      ],
      "agency": [
        "civic.agency"
      ],
      "media": [
        "pulse.media"
      ],
      "harbor.community": [
        "vault.harbor.community"
      ],
      "keystone.community": [
        "manuals.keystone.community"
      ],
      "nova.systems": [
        "endpoint.nova.systems"
      ],
      "stratus.systems": [
        "health.stratus.systems"
      ],
      "civic.agency": [
        "transparency.civic.agency",
        "citizens.civic.agency"
      ],
      "pulse.media": [
        "localdesk.pulse.media",
        "streams.pulse.media"
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
    "root_hints": "existing_root_server_[pc13]",
    "clients": "all_existing_client_hosts"
  },
  "zone_records": {
    "A": {
      "store.nimbus.tech": "existing_ipv4_of_pc8",
      "insights.nimbus.tech": "existing_ipv4_of_pc38",
      "division.orbit.tech": "existing_ipv4_of_pc24",
      "internal.orbit.tech": "existing_ipv4_of_pc18",
      "gateway.forge.tech": "existing_ipv4_of_pc22",
      "models.experiments.quantum.cloud": "existing_ipv4_of_pc6",
      "datasets.experiments.quantum.cloud": "existing_ipv4_of_pc9",
      "sandbox.quantum.cloud": "existing_ipv4_of_pc47",
      "build.matrix.cloud": "existing_ipv4_of_pc15",
      "secure.summit.academy": "existing_ipv4_of_pc23",
      "lessons.summit.academy": "existing_ipv4_of_pc41",
      "entry.cedar.academy": "existing_ipv4_of_pc33",
      "students.polaris.city": "existing_ipv4_of_pc10",
      "requests.riverton.city": "existing_ipv4_of_pc12",
      "statistics.highland.city": "existing_ipv4_of_pc5",
      "vault.harbor.community": "existing_ipv4_of_pc30",
      "manuals.keystone.community": "existing_ipv4_of_pc28",
      "endpoint.nova.systems": "existing_ipv4_of_pc46",
      "health.stratus.systems": "existing_ipv4_of_pc32",
      "transparency.civic.agency": "existing_ipv4_of_pc17",
      "citizens.civic.agency": "existing_ipv4_of_pc26",
      "localdesk.pulse.media": "existing_ipv4_of_pc35",
      "streams.pulse.media": "existing_ipv4_of_pc25",
      "mx.orbit.tech": "existing_ipv4_of_pc40",
      "mx.summit.academy": "existing_ipv4_of_pc4",
      "mx.division.orbit.tech": "existing_ipv4_of_pc24",
      "mx.citizens.civic.agency": "existing_ipv4_of_pc26"
    },
    "MX": {
      "orbit.tech": {
        "preference": 10,
        "exchange": "mx.orbit.tech"
      },
      "summit.academy": {
        "preference": 10,
        "exchange": "mx.summit.academy"
      },
      "division.orbit.tech": {
        "preference": 10,
        "exchange": "mx.division.orbit.tech"
      },
      "citizens.civic.agency": {
        "preference": 10,
        "exchange": "mx.citizens.civic.agency"
      }
    }
  }
}
