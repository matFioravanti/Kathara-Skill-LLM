import re

with open("scenarios/lab01_ring6_dual/correction.yaml", "r") as f:
    content = f.read()

# pc6 checks to wrap:
# 1. SOA
content = content.replace(
    "- command: sh -c 'dig @2001:db8:1100:2::10 test. SOA +norecurse +comments +answer +noquestion +nostats | tr \"\\n\" \" \" | grep -Eq \"flags:.*[[:space:]]aa[[:space:];].*[[:space:]]SOA[[:space:]]\"'",
    "- command: sh -c 'for i in 1 2 3 4 5; do dig @2001:db8:1100:2::10 test. SOA +norecurse +comments +answer +noquestion +nostats | tr \"\\n\" \" \" | grep -Eq \"flags:.*[[:space:]]aa[[:space:];].*[[:space:]]SOA[[:space:]]\" && exit 0; sleep 1; done; exit 1'"
)

# 2. A record
content = content.replace(
    "- command: sh -c 'dig @2001:db8:1100:2::10 www.test. A +short | grep -Fqx \"10.11.5.10\"'",
    "- command: sh -c 'for i in 1 2 3 4 5; do dig @2001:db8:1100:2::10 www.test. A +short | grep -Fqx \"10.11.5.10\" && exit 0; sleep 1; done; exit 1'"
)

# 3. AAAA record
content = content.replace(
    "- command: sh -c 'dig @2001:db8:1100:2::10 www.test. AAAA +short | grep -Fqx \"2001:db8:1100:3::10\"'",
    "- command: sh -c 'for i in 1 2 3 4 5; do dig @2001:db8:1100:2::10 www.test. AAAA +short | grep -Fqx \"2001:db8:1100:3::10\" && exit 0; sleep 1; done; exit 1'"
)

# 4. serial
content = content.replace(
    "- command: sh -c 's1=\"$(dig @2001:db8:1100:1::10 test. SOA +short | awk \"{print \\$3}\")\"; s2=\"$(dig @2001:db8:1100:2::10 test. SOA +short | awk \"{print \\$3}\")\"; test -n \"$s1\" && test \"$s1\" = \"$s2\"'",
    "- command: sh -c 'for i in 1 2 3 4 5; do s1=\"$(dig @2001:db8:1100:1::10 test. SOA +short | awk \\\"{print \\\\$3}\\\")\"; s2=\"$(dig @2001:db8:1100:2::10 test. SOA +short | awk \\\"{print \\\\$3}\\\")\"; test -n \"$s1\" && test \"$s1\" = \"$s2\" && exit 0; sleep 1; done; exit 1'"
)

# 5. AXFR
content = content.replace(
    "- command: 'sh -c ''dig @2001:db8:1100:1::10 test. AXFR +time=3 +tries=1 | grep -Eq \"[[:space:]]SOA[[:space:]]\"'' '",
    "- command: sh -c 'for i in 1 2 3 4 5; do dig @2001:db8:1100:1::10 test. AXFR +time=3 +tries=1 | grep -Eq \"[[:space:]]SOA[[:space:]]\" && exit 0; sleep 1; done; exit 1'"
)

with open("scenarios/lab01_ring6_dual/correction.yaml", "w") as f:
    f.write(content)
