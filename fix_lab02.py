import re

with open("scenarios/lab02_star7_mixed/correction.yaml", "r") as f:
    content = f.read()

# 1. Remove test: from authoritative
content = re.sub(r'(\s+)test:\n\s+- 2001:db8:1200:1::10\n\s+- 2001:db8:1200:4::10\n', '', content)

# 2. Fix TXT quoting
content = content.replace('""benchmark=dns-advanced""', '"\\"benchmark=dns-advanced\\""')

# 3. Fix zone regex
content = content.replace('"zone \\"test\\""', '"zone \\"test\\.?\\""')
content = content.replace('"zone \\"services\\.test\\""', '"zone \\"services\\.test\\.?\\""')

# 4. Wrap pc9 tests
content = content.replace(
    "- command: sh -c 'dig @2001:db8:1200:4::10 test. SOA +norecurse +comments +answer +noquestion +nostats | tr \"\\n\" \" \" | grep -Eq \"flags:.*[[:space:]]aa[[:space:];].*[[:space:]]SOA[[:space:]]\"'",
    "- command: sh -c 'for i in 1 2 3 4 5; do dig @2001:db8:1200:4::10 test. SOA +norecurse +comments +answer +noquestion +nostats | tr \"\\n\" \" \" | grep -Eq \"flags:.*[[:space:]]aa[[:space:];].*[[:space:]]SOA[[:space:]]\" && exit 0; sleep 1; done; exit 1'"
)

content = content.replace(
    "- command: sh -c 'dig @2001:db8:1200:4::10 www.test. A +short | grep -Fqx \"192.168.33.138\"'",
    "- command: sh -c 'for i in 1 2 3 4 5; do dig @2001:db8:1200:4::10 www.test. A +short | grep -Fqx \"192.168.33.138\" && exit 0; sleep 1; done; exit 1'"
)

content = content.replace(
    "- command: sh -c 'dig @2001:db8:1200:4::10 www.test. AAAA +short | grep -Fqx \"2001:db8:1200:4::11\"'",
    "- command: sh -c 'for i in 1 2 3 4 5; do dig @2001:db8:1200:4::10 www.test. AAAA +short | grep -Fqx \"2001:db8:1200:4::11\" && exit 0; sleep 1; done; exit 1'"
)

content = content.replace(
    "- command: sh -c 's1=\"$(dig @2001:db8:1200:1::10 test. SOA +short | awk \"{print \\$3}\")\"; s2=\"$(dig @2001:db8:1200:4::10 test. SOA +short | awk \"{print \\$3}\")\"; test -n \"$s1\" && test \"$s1\" = \"$s2\"'",
    "- command: sh -c 'for i in 1 2 3 4 5; do s1=\"$(dig @2001:db8:1200:1::10 test. SOA +short | awk \\\"{print \\\\$3}\\\")\"; s2=\"$(dig @2001:db8:1200:4::10 test. SOA +short | awk \\\"{print \\\\$3}\\\")\"; test -n \"$s1\" && test \"$s1\" = \"$s2\" && exit 0; sleep 1; done; exit 1'"
)

content = content.replace(
    "- command: 'sh -c ''dig @2001:db8:1200:1::10 test. AXFR +time=3 +tries=1 | grep -Eq \"[[:space:]]SOA[[:space:]]\"'' '",
    "- command: sh -c 'for i in 1 2 3 4 5; do dig @2001:db8:1200:1::10 test. AXFR +time=3 +tries=1 | grep -Eq \"[[:space:]]SOA[[:space:]]\" && exit 0; sleep 1; done; exit 1'"
)


with open("scenarios/lab02_star7_mixed/correction.yaml", "w") as f:
    f.write(content)

