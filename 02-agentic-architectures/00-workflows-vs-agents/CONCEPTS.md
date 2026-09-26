**Language:** Hinglish · [English](CONCEPTS.en.md)

# Workflows vs Agents: poora spectrum

> Sabse pehla sawaal jo har AI system banate waqt poochna chahiye:
> **"Steps kaun decide karega: mera code, ya LLM?"**

## 1. Teen building blocks (Anthropic ki "Building effective agents" taxonomy)

```
  kam autonomy, zyada control                               zyada autonomy, kam control
  ◄──────────────────────────────────────────────────────────────────────────────────►

  ┌─────────────────┐     ┌──────────────────────────┐     ┌──────────────────────────┐
  │ AUGMENTED LLM   │     │ WORKFLOWS                │     │ AUTONOMOUS AGENTS        │
  │                 │     │                          │     │                          │
  │ LLM + tools +   │     │ LLM calls ko CODE ke     │     │ LLM khud loop mein       │
  │ retrieval +     │     │ predefined path pe       │     │ decide karta hai: kaunsa │
  │ memory          │     │ chalao                   │     │ tool, kab, kitni baar,   │
  │                 │     │                          │     │ kab ruk jaana            │
  │ (ek call)       │     │ chaining, routing,       │     │                          │
  │                 │     │ parallel, orch-workers,  │     │ ReAct, plan-execute,     │
  │                 │     │ evaluator-optimizer      │     │ multi-agent...           │
  └─────────────────┘     └──────────────────────────┘     └──────────────────────────┘
        building block          code = control flow             LLM = control flow
```

- **Augmented LLM**: ek LLM call, lekin tools/retrieval/memory ke saath. Yahi har cheez ki "eent" (brick) hai.
- **Workflow**: tum (developer) flowchart pehle se likh dete ho. LLM har box ke andar kaam karta hai, lekin
  kaunsa box kab chalega, yeh **code** decide karta hai.
- **Agent**: flowchart hai hi nahi. LLM ko goal + tools milte hain, aur woh loop mein khud decide karta hai.

## 2. Same task, do tareeke (is folder ka demo)

Task: "user ke cart ka total (18% tax ke saath) batao aur friendly message likho"

```
WORKFLOW (spectrum_demo.run_as_chain)            AGENT (spectrum_demo.run_as_agent)
────────────────────────────────────             ──────────────────────────────────
 code: get_cart("u1")                             LLM: "pehle cart chahiye"
   │                                                │  tool_call get_cart(u1)
   ▼                                                ▼
 code: subtotal = sum(...)                        LLM: "ab total nikaalo"
   │                                                │  tool_call compute_total(4097)
   ▼                                                ▼
 code: compute_total(subtotal)                    LLM: final friendly message
   │
   ▼
 LLM: sirf message likho      ← 1 LLM call        ← 3 LLM calls
```

| | Workflow | Agent |
|---|---|---|
| Steps kaun decide karta hai | Code | LLM |
| Predictability | High (same input -> same path) | Kam (path badal sakta hai) |
| Cost / latency | Kam (fixed calls) | Zyada (loop, har step pe poori history) |
| Naye/unexpected sawaal | Nahi sambhalta | Sambhal leta hai ("mera 2nd cart?") |
| Testing | Aasan (har step unit test) | Mushkil (evals chahiye) |
| Failure mode | Galat input pe rigid | Loop, galat tool, hallucinated args |

## 3. Decision guide: kaunsa architecture chunein?

```
                    Kya ek LLM call (+ acha prompt / RAG) se kaam ho jaata hai?
                                 │
                   ┌──── haan ───┴──── nahi ────┐
                   ▼                            ▼
           AUGMENTED LLM             Kya steps pehle se pata hain?
           (yahin ruk jao!)                     │
                                ┌──── haan ─────┴───── nahi ─────┐
                                ▼                                ▼
                  Steps sequential hain?              Subtasks input pe depend
                        │                             karte hain, lekin ek hi
             ┌── haan ──┴── nahi ──┐                  baar plan kaafi hai?
             ▼                     ▼                         │
      PROMPT CHAINING     Input ke type pe        ┌── haan ──┴── nahi ──┐
       (01)               alag handling?          ▼                      ▼
                          │                ORCHESTRATOR-          Open-ended, kitne
                ┌─ haan ──┴── nahi ─┐       WORKERS (08)          steps pata nahi,
                ▼                   ▼                              environment se
            ROUTING (02)     Independent parts /                  feedback chahiye?
                             confidence chahiye?                         │
                                    │                                    ▼
                                    ▼                              AGENT (ReAct 04,
                            PARALLELIZATION (03)                   plan-execute 05...)

   Quality iteratively sudhaarni hai, aur clear rubric hai?  ──►  EVALUATOR-OPTIMIZER (07)
   (yeh kisi bhi upar wale ke saath combine hota hai)
```

**Golden rule:** sabse simple cheez se shuru karo. Agent tabhi lao jab workflow genuinely kam pad raha ho.
Complexity ka matlab: zyada cost, zyada latency, zyada debugging.

## 4. Patterns ek nazar mein (is section ke folders)

| Folder | Pattern | Type | Ek line |
|---|---|---|---|
| 01 | Prompt chaining | Workflow | Sequential steps + code gates |
| 02 | Routing | Workflow | Classify -> specialised handler/model |
| 03 | Parallelization | Workflow | Sectioning (split) + Voting (repeat) |
| 07 | Evaluator-optimizer | Workflow | Generate -> judge -> feedback loop |
| 08 | Orchestrator-workers | Workflow (dynamic) | LLM runtime pe subtasks banata hai |
| 04+ | ReAct, plan-execute, reflection, ... | Agent | LLM loop control karta hai |

Orchestrator-workers "border" pe hai: plan LLM banata hai (agent jaisa), lekin execution
code ke fixed dhaanche mein hota hai (workflow jaisa).

## 5. Production pitfalls

- **Agent jab workflow kaafi tha**: 5x cost, aur har run alag. Pehle workflow try karo.
- **Math/lookup LLM se karwana**: `compute_total` code mein hai, LLM mein nahi. LLM se sirf woh karwao jo sirf LLM kar sakta hai.
- **Agent bina guards ke**: max_steps, tool errors model ko wapas, human approval (agentkit `Agent` mein built-in).
- **Frameworks ka jaldi use**: LangGraph/CrewAI achhe hain, lekin pehle raw pattern samjho (yahi repo ka maqsad).

## 6. Is project mein kaise use ho raha hai

| Concept | Kahan |
|---|---|
| Shared tools (dono approach same tools) | `spectrum_demo.py` -> `get_cart`, `compute_total` (`@tool`) |
| Workflow: code calls tools directly | `run_as_chain()` -> `get_cart.fn(...)`, `compute_total.fn(...)`, phir ek `llm.complete` |
| Agent: LLM decides | `run_as_agent()` -> `agentkit.Agent` loop with tools |
| Cost comparison | `main.py` dono ke "LLM calls" print karta hai (1 vs 3) |
| Error recovery (agent) | `test_agent_recovers_from_bad_user_id` -> tool error model ko wapas milta hai |
