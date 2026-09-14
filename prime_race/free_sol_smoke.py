import os, base64, threading, time, json
from flask import Flask, jsonify
from openai import OpenAI
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

app = Flask(__name__)
state = {"status":"BOOTING","result":None,"error":None}

def load_key():
    ct = os.environ["OPENAI_API_KEY_CIPHERTEXT"]
    priv_der = base64.b64decode(os.environ["RACE_PRIVATE_KEY_DER_B64"])
    raw = base64.urlsafe_b64decode(ct + "=" * ((4-len(ct)%4)%4))
    priv = serialization.load_der_private_key(priv_der, password=None)
    return priv.decrypt(raw, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)).decode().strip()

def run():
    state["status"] = "RUNNING"
    try:
        client = OpenAI(api_key=load_key())
        t0 = time.time()
        r = client.responses.create(
            model="gpt-5.6-sol",
            reasoning={"effort":"low"},
            instructions="Return exactly FREE_SOL_OK and nothing else.",
            input="Free-token eligibility smoke test.",
            store=False,
        )
        state["result"] = {
            "model": getattr(r, "model", None),
            "response_id": getattr(r, "id", None),
            "output": r.output_text,
            "elapsed_sec": round(time.time()-t0, 3),
            "usage": getattr(getattr(r, "usage", None), "model_dump", lambda:None)(),
        }
        state["status"] = "COMPLETE"
        print("FREE_SOL_RESULT=" + json.dumps(state["result"], separators=(",",":")), flush=True)
    except Exception as e:
        state["error"] = f"{type(e).__name__}: {e}"
        state["status"] = "FAILED"
        print("FREE_SOL_FAILED " + state["error"], flush=True)

@app.get("/")
def root():
    return jsonify(state)

threading.Thread(target=run, daemon=True).start()
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT","10000")))
