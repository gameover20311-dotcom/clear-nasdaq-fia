import random

def build(seed, n=100):
    rng=random.Random(seed)
    return [rng.randint(1, 1000) for _ in range(n)]
