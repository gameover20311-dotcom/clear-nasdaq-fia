import hashlib, random
import prime_repair_eval as core

def generate(seed, count=10):
    rng=random.Random(seed); out=[]
    for i in range(count):
        a=rng.randint(5,40); token=hashlib.sha256(f"{seed}:{i}".encode()).hexdigest()[:8]
        values=[f"Q equals {a}",f"Q is greater than {a}",f"Q is less than {a}","Cannot determine from supplied facts"]
        rng.shuffle(values); options=dict(zip("ABCD",values)); answer="ABCD"[values.index("Cannot determine from supplied facts")]
        out.append(core.Task(f"UN-{i:02d}-{token}","missing_information","Which conclusion follows from the supplied facts?",f"Q = {a} + R. No value, bound, or distribution for R is supplied.",options,answer))
    return out
