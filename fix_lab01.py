with open("scenarios/lab01_ring6_dual/correction.yaml", "r") as f:
    content = f.read()
content = content.replace("dns:# Checker compatibility", "dns:\n# Checker compatibility")
with open("scenarios/lab01_ring6_dual/correction.yaml", "w") as f:
    f.write(content)
