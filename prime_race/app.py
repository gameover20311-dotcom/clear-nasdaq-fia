import os, json, time, threading, random, base64, math
from pathlib import Path
from flask import Flask, jsonify
from openai import OpenAI

HERE=Path(__file__).resolve().parent
PUB=json.loads((HERE/'benchmark_smoke.json').read_text())
POLICY=(HERE/'ultra_policy.txt').read_text()
ANS=json.loads(base64.b64decode(os.environ['RACE_ANSWERS_B64']).decode())['answers']
SCHEMA={"type":"object","properties":{"choice":{"type":"string","enum":["A","B","C","D"]},"confidence":{"type":"integer","minimum":0,"maximum":100},"reason":{"type":"string"}},"required":["choice","confidence","reason"],"additionalProperties":False}
app=Flask(__name__)
state={"status":"BOOTING","result":None,"error":None}
client=OpenAI(api_key=os.environ['OPENAI_API_KEY'])

def fmt_task(t):
    opts='\n'.join(f"{k}. {v}" for k,v in t['options'].items())
    return f"TASK {t['id']}\nCATEGORY: {t['category']}\nQUESTION:\n{t['question']}\n\nEVIDENCE/CONTEXT:\n{t['context']}\n\nOPTIONS:\n{opts}\n\nChoose exactly one option."

def call(model,instructions,input_text,tag,effort='high'):
    last=None
    for attempt in range(7):
        t0=time.time()
        try:
            r=client.responses.create(model=model,reasoning={"effort":effort},instructions=instructions,input=input_text,
                text={"format":{"type":"json_schema","name":"bench_answer","schema":SCHEMA,"strict":True}},store=False)
            txt=r.output_text
            parsed=json.loads(txt)
            rec={"tag":tag,"response_id":getattr(r,'id',None),"model":getattr(r,'model',None),"elapsed_sec":round(time.time()-t0,3),
                 "usage":getattr(getattr(r,'usage',None),'model_dump',lambda:None)(),"output":parsed}
            print('CALL_OK '+json.dumps(rec,separators=(',',':')),flush=True)
            return parsed,rec
        except Exception as e:
            last=e
            msg=f"{type(e).__name__}: {e}"
            print(f"CALL_RETRY tag={tag} attempt={attempt+1} err={msg[:500]}",flush=True)
            time.sleep(min(2**attempt,30))
    raise RuntimeError(f"call failed {tag}: {last}")

def plain(model,t,arm):
    instr="You are being benchmarked on a forensic software/scientific reasoning task. Use only supplied evidence. Do not assume missing facts. Return the best option."
    return call(model,instr,fmt_task(t),f'{arm}_{t["id"]}')

def prime(t):
    base=fmt_task(t)
    d,_=call('gpt-5.6-sol',POLICY+"\nROLE: initial analyst. Build the strongest provisional answer.",base,f'prime_draft_{t["id"]}')
    a,_=call('gpt-5.6-sol',POLICY+"\nROLE: ATTACK A. Try to prove the draft wrong. Pick the strongest alternative if warranted.",base+"\n\nDRAFT:\n"+json.dumps(d),f'prime_attackA_{t["id"]}')
    b,_=call('gpt-5.6-sol',POLICY+"\nROLE: ATTACK B. Try to prove ATTACK A wrong; identify what survives both attacks.",base+"\n\nDRAFT:\n"+json.dumps(d)+"\nATTACK_A:\n"+json.dumps(a),f'prime_attackB_{t["id"]}')
    j,_=call('gpt-5.6-sol',POLICY+"\nROLE: final judge. Choose the weakest defensible option. Do not treat repeated Sol calls as independent evidence.",base+"\n\nDRAFT:\n"+json.dumps(d)+"\nATTACK_A:\n"+json.dumps(a)+"\nATTACK_B:\n"+json.dumps(b),f'prime_final_{t["id"]}')
    return j

def score(outputs,tasks):
    rows=[]
    for t in tasks:
        meta=ANS[t['id']]; got=outputs[t['id']]['choice']; ok=got==meta['answer']
        rows.append({"id":t['id'],"got":got,"expected":meta['answer'],"ok":ok,"severity":meta['severity'],"control":meta['control']})
    return {"correct":sum(r['ok'] for r in rows),"n":len(rows),"rows":rows}

def race():
    state['status']='RUNNING'
    try:
        tasks=list(PUB['tasks'])
        limit=int(os.getenv('RACE_LIMIT','2'))
        tasks=tasks[:limit]
        outputs={"sol_plain":{},"astra_plain":{},"prime_sol":{}}
        for t in tasks:
            outputs['astra_plain'][t['id']]=plain('gpt-6-astra',t,'astra_plain')[0]
            outputs['sol_plain'][t['id']]=plain('gpt-5.6-sol',t,'sol_plain')[0]
            outputs['prime_sol'][t['id']]=prime(t)
        scores={k:score(v,tasks) for k,v in outputs.items()}
        result={"kind":"SMOKE_ONLY_NO_VICTORY_CLAIM","tasks":[t['id'] for t in tasks],"scores":scores,"outputs":outputs}
        state['result']=result; state['status']='COMPLETE'
        print('RACE_RESULT_JSON='+json.dumps(result,separators=(',',':')),flush=True)
    except Exception as e:
        state['error']=f"{type(e).__name__}: {e}"; state['status']='FAILED'
        print('RACE_FAILED '+state['error'],flush=True)

@app.get('/')
def root(): return jsonify({"service":"prime-astra-race","status":state['status']})
@app.get('/result')
def result(): return jsonify(state)

threading.Thread(target=race,daemon=True).start()
if __name__=='__main__':
    app.run(host='0.0.0.0',port=int(os.getenv('PORT','10000')))
