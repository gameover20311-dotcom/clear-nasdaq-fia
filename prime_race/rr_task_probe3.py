import prime_repair_eval as core

def one():
    return core.Task("Y","uncertain","Which conclusion follows?","Q = 10 + R. No value for R is supplied.",{"A":"Q is 10","B":"Q is above 10","C":"Q is below 10","D":"Cannot determine"},"D")
