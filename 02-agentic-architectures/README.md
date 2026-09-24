# 02 · Agentic Architectures

Is section mein har popular agent architecture ka **from-scratch implementation** hai: koi LangChain/LangGraph
magic nahi, sirf `agentkit` (`Agent`, `tool`, `llm_json`, `get_llm`). Har folder mein:

- `CONCEPTS.md`: concept Hinglish mein, flow diagrams, variants, trade-offs, aur "is project mein kaise use ho raha hai"
- `TESTING.md`: kaise chalayein, kya dekhein, aur tinker exercises
- `main.py --offline`: bina API key ke flow dekho; `pytest <folder>`: offline tests

## 1. Pehle ek basic sawaal: Workflow ya Agent?

```
  ZYADA CONTROL / PREDICTABLE                                      ZYADA AUTONOMY / FLEXIBLE
  ◄──────────────────────────────────────────────────────────────────────────────────────►
  single LLM   prompt      routing   parallel-  orchestrator-  plan-and-   ReAct     multi-agent
  call         chaining              ization    workers        execute     agent     systems
  │                                                                                      │
  └── WORKFLOW: code decides the path ──┘  └── AGENT: LLM decides the path ──────────────┘
```

- **Workflow:** steps ka order **code** mein fixed hai; LLM sirf har step ka kaam karta hai. Sasta, fast, test karna aasaan.
- **Agent:** LLM khud decide karta hai agla step kya hai (loop + tools). Flexible, lekin mehnga, slow, unpredictable.

**Golden rule (Anthropic "Building effective agents"):** sabse simple cheez se shuru karo. Agent tabhi banao jab
workflow se kaam na chale.

## 2. Architecture families ka map

```
                               AGENTIC ARCHITECTURES
                                        │
         ┌──────────────────────────────┼───────────────────────────────┐
         │                              │                               │
   WORKFLOW PATTERNS              SINGLE-AGENT LOOPS              AGENT CAPABILITIES
   (code controls flow)          (LLM controls flow)             (kisi bhi loop mein add karo)
         │                              │                               │
   01 prompt chaining           04 ReAct                        06 reflection / Reflexion
   02 routing                   05 plan-and-execute             11 human-in-the-loop
   03 parallelization           09 ReWOO                        12 memory
      (sectioning + voting)     10 tree of thoughts
   07 evaluator-optimizer          (search over thoughts)
   08 orchestrator-workers
         │                              │                               │
         └──────────────► 06-multi-agent-systems (repo ka section 6) ◄──┘
                          (kai agents, roles, communication)
```

## 3. Saare projects ek nazar mein

| # | Folder | Pattern | Ek line mein | LLM calls | Kab use karein |
|---|---|---|---|---|---|
| 00 | `00-workflows-vs-agents` | Spectrum + decision guide | same task: workflow vs agent, side by side | - | shuru yahin se karo |
| 01 | `01-prompt-chaining` | Workflow | output of step N = input of step N+1, beech mein gates | fixed N | task clearly steps mein toot-ta hai |
| 02 | `02-routing` | Workflow | classifier input ko sahi specialist/model pe bhejta hai | 1 + 1 | alag type ke inputs, alag handling |
| 03 | `03-parallelization` | Workflow | **sectioning** (alag sub-tasks parallel) + **voting** (same task N baar, majority) | N parallel | speed ya confidence chahiye |
| 04 | `04-react` | Agent | Thought → Action → Observation loop (text parsing vs native tool calling) | per step | open-ended, tool-heavy tasks |
| 05 | `05-plan-and-execute` | Agent | planner plan banata hai, executor steps karta hai, replanner adjust karta hai | plan + per step | lambe multi-step tasks |
| 06 | `06-reflection` | Capability | generate → critique → revise; Reflexion = tests + lessons memory | 2 per round | quality > latency, clear criteria |
| 07 | `07-evaluator-optimizer` | Workflow | generator + alag evaluator loop jab tak criteria pass na ho | 2 per round | measurable quality bar |
| 08 | `08-orchestrator-workers` | Workflow/agent | orchestrator dynamically sub-tasks banata hai, workers karte hain, synthesizer jodta hai | 1 + N + 1 | sub-tasks pehle se pata nahi |
| 09 | `09-rewoo` | Agent | saare tool calls pehle plan (#E1, #E2), phir bina LLM execute, phir solve | **2** | predictable tool chains, token bachana |
| 10 | `10-tree-of-thoughts` | Agent (search) | thoughts ka tree, LLM propose + evaluate, BFS/DFS search | bahut zyada | puzzles, planning, backtracking chahiye |
| 11 | `11-human-in-the-loop` | Capability | risk policy, approve/edit/reject, pause + JSON checkpoint + resume, escalation | - | koi bhi risky/irreversible action |
| 12 | `12-memory` | Capability | short-term (window/summary), long-term (semantic + episodic), extraction | +1 per session | personal assistants, long chats |

## 4. Kaunsa architecture kab? (decision flow)

```
                         Naya task aaya
                               │
               Ek LLM call (+ achha prompt/RAG) se ho jayega?
                     │yes                    │no
                     ▼                       ▼
               single call        Steps pehle se pata hain aur fixed hain?
               (agent mat banao)       │yes                          │no
                                       ▼                              ▼
                          Inputs alag-alag type ke hain?     Steps ek doosre ke results
                            │yes          │no                pe depend karte hain?
                            ▼             ▼                    │no              │yes
                        02 routing   Independent sub-tasks?    ▼                ▼
                                      │yes       │no      08 orchestrator   Saare tool calls
                                      ▼          ▼         -workers         pehle plan ho sakte?
                               03 parallel-  01 prompt                       │yes         │no
                                  ization     chaining                       ▼            ▼
                                                                         09 ReWOO    Task lamba hai
                                                                                     (5+ steps)?
                                                                                   │yes      │no
                                                                                   ▼         ▼
                                                                            05 plan-and-  04 ReAct
                                                                               execute
            Galat early decision bahut costly? Search chahiye? ───────────► 10 tree of thoughts

  Upar wale kisi pe bhi ADD karo:
    Quality bar clear hai (tests/rubric)?        → 06 reflection / 07 evaluator-optimizer
    Irreversible/risky actions?                  → 11 human-in-the-loop
    Sessions ke beech yaad rakhna hai?           → 12 memory
    Ek agent ke liye kaam bahut bada/alag roles? → section 06-multi-agent-systems
```

## 5. Recommended order

1. `00-workflows-vs-agents`: mindset set karo
2. `01-prompt-chaining` → `02-routing` → `03-parallelization`: workflow basics
3. `04-react`: **sabse important**: har agent ka core loop
4. `05-plan-and-execute` → `09-rewoo`: planning ke do extremes (adaptive vs cheap)
5. `08-orchestrator-workers`: dynamic decomposition (multi-agent ki taraf pehla kadam)
6. `06-reflection` → `07-evaluator-optimizer`: quality loops
7. `10-tree-of-thoughts`: search (advanced, mehnga)
8. `11-human-in-the-loop` → `12-memory`: production capabilities

## 6. Chalane ka common tareeka

```bash
# repo root se
pip install -e ".[all]"
cp .env.example .env   # LLM_MODEL=groq:... / gemini:... / ollama:... + key

python 02-agentic-architectures/04-react/main.py --offline      # bina key
python 02-agentic-architectures/04-react/main.py "your question" # real LLM
pytest 02-agentic-architectures -q                               # saare offline tests
```

`AGENT_VERBOSE=0` se trace band, `AGENT_TRACE_FILE=trace.jsonl` se har step JSONL mein.
