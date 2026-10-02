# Reproduce: .venv/bin/python reports/2026-10-02/nc_claim_check.py
"""Independent check of nonclassical_supreme.superpose claims."""
import random, string, time
from sovereign_agent.nonclassical_supreme import superpose
from sovereign_agent.nonclassical_supreme.quality_proof import quality_proof

rng = random.Random(42)
words = ["safety","cat","mat","phase","bot","price","alert","stock","sleep","story","video","refund",
         "cancel","order","login","password","weather","rain","music","course","python","discord"]
def rand_text(n): return " ".join(rng.choice(words) for _ in range(n))

# 1) Does the "quantum" pipeline ever pick something other than plain word-overlap argmax?
agree = total = 0
for _ in range(20000):
    q = rand_text(rng.randint(2,6)); cands = list({rand_text(rng.randint(2,6)) for _ in range(rng.randint(2,8))})
    nc = superpose.process(q, cands, seed=0)["result"]
    sims = [superpose.similarity(q, c) for c in cands]
    best = max(sims)
    agree += superpose.similarity(q, nc) == best; total += 1
print(f"1) NC top answer == plain text-overlap best match: {agree}/{total} = {agree/total:.4%}")

# 2) Speed: plain overlap argmax vs full NC pipeline
cands = [f"candidate answer number {i} with some words" for i in range(8)]
q = "which candidate best answers the question about words and numbers"
def plain(q, cands): return max(cands, key=lambda c: superpose.similarity(q, c))
for name, fn in [("NC pipeline", lambda: superpose.process(q, cands, seed=0)), ("plain overlap argmax", lambda: plain(q, cands))]:
    for _ in range(200): fn()
    t=time.perf_counter(); 
    for _ in range(5000): fn()
    print(f"2) {name}: {(time.perf_counter()-t)/5000*1e6:.1f} microseconds/call")

# 3) Meaning, not word overlap: paraphrase tests (expected answer shares few/no words)
cases = [
 ("how do I stop paying every month", ["cancel your subscription in account settings", "how do I pay with paypal every month", "track your order status"], 0),
 ("my bot quit sending alerts", ["restart the notification bot if alerts stopped", "how do I get a bot to quit", "pricing for sending more alerts"], 0),
 ("I forgot how to get into my account", ["reset your password from the login page", "how to delete my account", "I forgot my order number"], 0),
 ("something to listen to while falling asleep", ["calm bedtime story audiobook", "listen to while falling: a skydiving guide", "wake up alarm sounds"], 0),
 ("is it going to be wet outside tomorrow", ["rain forecast for tomorrow", "is it going outside to be tomorrow wet paint", "sunscreen tips"], 0),
]
ok = 0
for q, c, exp in cases:
    r = superpose.process(q, c, seed=0)
    hit = r["result"] == c[exp]; ok += hit
    print(f"3) {'PASS' if hit else 'FAIL'} q={q!r} -> {r['result']!r} (confidence {r['confidence']})")
print(f"3) paraphrase accuracy: {ok}/{len(cases)}")

# 4) The built-in quality proof
qp = quality_proof()
print("4) built-in quality_proof:", [(t['task'], t.get('accuracy')) for t in qp['tasks']])
