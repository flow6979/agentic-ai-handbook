# Routing

## 1. Concept kya hai?

Input ko pehle **classify** karo, phir use us **specialised handler** ke paas bhejo jo us type ke liye bana hai.
Jaise hospital reception: patient ko dekh ke decide karta hai ki cardiology jaana hai ya orthopedics.

```
                           ┌───────────────┐
                    ┌─────►│ billing       │  (billing prompt, cheap model)
                    │      └───────────────┘
  ticket ──►[ROUTER]├─────►│ technical     │  (engineer prompt)
                    │      └───────────────┘
                    ├─────►│ refund        │  (refund policy prompt)
                    │      └───────────────┘
                    ├─────►│ general       │
                    │      └───────────────┘
                    └─────►  HUMAN (low confidence / router fail)
```

**Kyun?** Ek hi prompt mein saare cases handle karoge to prompt bada aur confusing ho jaata hai, aur
ek case ko optimise karne se doosra bigad jaata hai. Routing = **separation of concerns**.

## 2. Router ke subtypes

| Type | Kaise | Pros | Cons |
|---|---|---|---|
| **Rule-based** | keywords / regex | free, 0 ms, predictable, testable | brittle: "paisa wapas chahiye" miss |
| **LLM classifier** | LLM se `{route, confidence, reason}` JSON | natural language samajhta hai | cost + latency, kabhi galat |
| **Embedding / semantic** | input ka embedding, har route ke examples se nearest | sasta, fast, no generation | examples chahiye, threshold tuning |
| **Hybrid** | rules pehle, phir LLM, low confidence -> human | best of both | thoda complex |
| **Model routing** | query difficulty dekh ke cheap vs strong model | bada cost saving | galat route = poor answer |

```
HYBRID ROUTER (is project ka hybrid_route):

  text ──► rule_route() ──match──► route (method=rule, confidence=1.0)     ← free
              │
           no match
              ▼
          llm_route() ──JSON invalid──► general + needs_human (method=fallback)
              │
          confidence < 0.6 ? ──yes──► needs_human (escalate)
              │ no
              ▼
          route (method=llm)
```

### Model routing (cost optimisation)

```
 query ──► complexity_score() ──► score < 2 ──► CHEAP model  (8B, fast, ~10x sasta)
                                  score >= 2 ──► STRONG model (70B / frontier)
```
Real systems mein 60-80% queries easy hoti hain -> sasta model unhe handle kar le to bahut bachat.
Score heuristic se, chhote classifier se, ya LLM se bhi nikal sakte ho.

## 3. Confidence aur escalation

LLM router ko **confidence** bhi dene ko bolo. Low confidence = "mujhe pata nahi" -> human ya safe default.
Dhyan do: LLM ka self-reported confidence perfectly calibrated nahi hota; production mein eval set pe threshold tune karo.

## 4. Kab use karein / kab nahi

Use karo jab:
- Clearly distinct categories hain jinhe alag handling chahiye.
- Categories accurately classify ho sakti hain (rules ya LLM se).
- Cost bachana hai (easy -> sasta model).

Mat karo jab:
- Sirf 1-2 cases hain; ek achha prompt kaafi hai.
- Categories overlap karti hain bahut zyada (ek ticket billing + technical dono) -> multi-label / orchestrator socho.

## 5. Production pitfalls

- **Rule order**: "refund for double payment" billing bhi hai, refund bhi. Rules ka order = priority (`RULES` list).
- **Router failure pe crash**: JSON galat aaya to safe default + escalate (`method=fallback`).
- **Silent misroutes**: har decision log karo (route, method, confidence) aur weekly sample review karo.
- **Router ke liye strong model**: router ko sasta/fast model do; woh sirf classify karta hai.
- **Category drift**: naye type ke tickets aane lagte hain -> "general" bhar jaata hai. Metrics dekho.

## 6. Is project mein kaise use ho raha hai

| Concept | File / function |
|---|---|
| Rule-based router + priority order | `routing_router.py` -> `RULES`, `rule_route()` |
| LLM classifier (structured) | `llm_route()` -> `llm_json(..., RouteDecision)` with `ROUTER_SYSTEM` |
| Hybrid + escalation + safe fallback | `hybrid_route()` -> `Routed(method, needs_human)` |
| Model routing | `complexity_score()`, `pick_model()` |
| Specialised handlers | `HANDLER_PROMPTS` dict, `handle_ticket()` |
| Alag models per role | `main.py`: `ROUTER_MODEL`, `CHEAP_MODEL`, `STRONG_MODEL` env vars |
