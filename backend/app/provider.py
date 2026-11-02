import random, time

def lookup(indicator: str) -> dict:
    time.sleep(random.uniform(0.1, 0.4))
    verdict = random.choice(["malicious", "suspicious", "clean"])
    families = random.sample(["Emotet", "AgentTesla", "Qakbot", "Mirai", "Cobalt Strike"], 2) if verdict != "clean" else []
    return {"verdict": verdict, "score": random.randint(0, 100), "malware_families": families}
