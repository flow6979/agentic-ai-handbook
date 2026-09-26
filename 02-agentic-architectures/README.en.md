**Language:** [Hinglish](README.md) · English

# 02 · Agentic Architectures

This section contains a **from-scratch implementation** of every popular agent architecture: no LangChain/LangGraph
magic, just `agentkit` (`Agent`, `tool`, `llm_json`, `get_llm`). Every folder has:

- `CONCEPTS.md`: the concept explained, with flow diagrams, variants, trade-offs, and "how this project uses it"
- `TESTING.md`: how to run it, what to look for, and tinker exercises
- `main.py --offline`: see the flow without an API key; `pytest <folder>`: offline tests

## 1. First, a basic question: Workflow or Agent?

```
  MORE CONTROL / PREDICTABLE                                       MORE AUTONOMY / FLEXIBLE
  ◄──────────────────────────────────────────────────────────────────────────────────────►
  single LLM   prompt      routing   parallel-  orchestrator-  plan-and-   ReAct     multi-agent
  call         chaining              ization    workers        execute     agent     systems
  │                                                                                      │
  └── WORKFLOW: code decides the path ──┘  └── AGENT: LLM decides the path ──────────────┘
```

- **Workflow:** the order of steps is fixed in **code**; the LLM only does the work inside each step. Cheap, fast, easy to test.
- **Agent:** the LLM itself decides what the next step is (loop + tools). Flexible, but expensive, slow and unpredictable.

**Golden rule (Anthropic, "Building effective agents"):** start with the simplest thing. Build an agent only when
a workflow cannot do the job.

## 2. Map of architecture families

```
                               AGENTIC ARCHITECTURES
                                        │
         ┌──────────────────────────────┼───────────────────────────────┐
         │                              │                               │
   WORKFLOW PATTERNS              SINGLE-AGENT LOOPS              AGENT CAPABILITIES
   (code controls flow)          (LLM controls flow)             (add to any loop)
         │                              │                               │
   01 prompt chaining           04 ReAct                        06 reflection / Reflexion
   02 routing                   05 plan-and-execute             11 human-in-the-loop
   03 parallelization           09 ReWOO                        12 memory
      (sectioning + voting)     10 tree of thoughts
   07 evaluator-optimizer          (search over thoughts)
   08 orchestrator-workers
         │                              │                               │
         └──────────────► 06-multi-agent-systems (section 6 of the repo) ◄──┘
                          (many agents, roles, communication)
```

## 3. All projects at a glance

| # | Folder | Pattern | In one line | LLM calls | When to use |
|---|---|---|---|---|---|
| 00 | `00-workflows-vs-agents` | Spectrum + decision guide | same task: workflow vs agent, side by side | - | start here |
| 01 | `01-prompt-chaining` | Workflow | output of step N = input of step N+1, with gates in between | fixed N | the task clearly breaks into steps |
| 02 | `02-routing` | Workflow | a classifier sends the input to the right specialist/model | 1 + 1 | different kinds of input need different handling |
| 03 | `03-parallelization` | Workflow | **sectioning** (different sub-tasks in parallel) + **voting** (same task N times, majority) | N parallel | you need speed or confidence |
| 04 | `04-react` | Agent | Thought → Action → Observation loop (text parsing vs native tool calling) | per step | open-ended, tool-heavy tasks |
| 05 | `05-plan-and-execute` | Agent | a planner makes the plan, an executor runs the steps, a replanner adjusts | plan + per step | long multi-step tasks |
| 06 | `06-reflection` | Capability | generate → critique → revise; Reflexion = tests + lessons memory | 2 per round | quality > latency, clear criteria |
| 07 | `07-evaluator-optimizer` | Workflow | generator + separate evaluator loop until the criteria pass | 2 per round | a measurable quality bar |
| 08 | `08-orchestrator-workers` | Workflow/agent | the orchestrator creates sub-tasks dynamically, workers do them, a synthesizer combines | 1 + N + 1 | sub-tasks are not known in advance |
| 09 | `09-rewoo` | Agent | plan all tool calls first (#E1, #E2), then execute without the LLM, then solve | **2** | predictable tool chains, saving tokens |
| 10 | `10-tree-of-thoughts` | Agent (search) | a tree of thoughts, LLM proposes + evaluates, BFS/DFS search | very many | puzzles, planning, when backtracking is needed |
| 11 | `11-human-in-the-loop` | Capability | risk policy, approve/edit/reject, pause + JSON checkpoint + resume, escalation | - | any risky or irreversible action |
| 12 | `12-memory` | Capability | short-term (window/summary), long-term (semantic + episodic), extraction | +1 per session | personal assistants, long chats |

## 4. Which architecture when? (decision flow)

```
                         A new task arrives
                               │
               Can one LLM call (+ a good prompt/RAG) do it?
                     │yes                    │no
                     ▼                       ▼
               single call        Are the steps known in advance and fixed?
               (don't build an agent)  │yes                          │no
                                       ▼                              ▼
                          Are inputs of different kinds?     Do steps depend on each
                            │yes          │no                other's results?
                            ▼             ▼                    │no              │yes
                        02 routing   Independent sub-tasks?    ▼                ▼
                                      │yes       │no      08 orchestrator   Can all tool calls
                                      ▼          ▼         -workers         be planned upfront?
                               03 parallel-  01 prompt                       │yes         │no
                                  ization     chaining                       ▼            ▼
                                                                         09 ReWOO    Is the task long
                                                                                     (5+ steps)?
                                                                                   │yes      │no
                                                                                   ▼         ▼
                                                                            05 plan-and-  04 ReAct
                                                                               execute
            Is a wrong early decision very costly? Need search? ────────► 10 tree of thoughts

  ADD on top of any of the above:
    Clear quality bar (tests/rubric)?            → 06 reflection / 07 evaluator-optimizer
    Irreversible/risky actions?                  → 11 human-in-the-loop
    Need to remember across sessions?            → 12 memory
    Work too big for one agent / distinct roles? → section 06-multi-agent-systems
```

## 5. Recommended order

1. `00-workflows-vs-agents`: set the mindset
2. `01-prompt-chaining` → `02-routing` → `03-parallelization`: workflow basics
3. `04-react`: **the most important one**: the core loop of every agent
4. `05-plan-and-execute` → `09-rewoo`: two extremes of planning (adaptive vs cheap)
5. `08-orchestrator-workers`: dynamic decomposition (first step towards multi-agent)
6. `06-reflection` → `07-evaluator-optimizer`: quality loops
7. `10-tree-of-thoughts`: search (advanced, expensive)
8. `11-human-in-the-loop` → `12-memory`: production capabilities

## 6. The common way to run things

```bash
# from the repo root
pip install -e ".[all]"
cp .env.example .env   # LLM_MODEL=groq:... / gemini:... / ollama:... + key

python 02-agentic-architectures/04-react/main.py --offline      # no key
python 02-agentic-architectures/04-react/main.py "your question" # real LLM
pytest 02-agentic-architectures -q                               # all offline tests
```

`AGENT_VERBOSE=0` turns the trace off, `AGENT_TRACE_FILE=trace.jsonl` writes every step as JSONL.
