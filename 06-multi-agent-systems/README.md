# 06 · Multi-Agent Systems (with Roles)

> Ek agent = ek LLM + tools + loop. **Multi-agent system** = kai agents, har ek ka alag **role**, jo milke ek goal pe kaam karte hain.

## Multi-agent system banta kis se hai?

```
┌───────────────────────────────────────────────────────────────────┐
│                       MULTI-AGENT SYSTEM                          │
│                                                                   │
│  1. ROLES        kaun kya hai (persona, goal, tools, rules)       │
│  2. GOAL         poori team ka common objective                   │
│  3. CONTEXT      shared (board/transcript) vs private (per-role)  │
│  4. COORDINATION agla kaun kaam karega? (code / manager / peer)   │
│  5. TERMINATION  kab rukna hai? (done / budget / guard)           │
│  6. COMMUNICATION messages kaise jaate hain → section 05          │
└───────────────────────────────────────────────────────────────────┘
```

| Building block | Sawaal | Galat hua to |
|---|---|---|
| Roles | Har agent ki zimmedari kya hai? | Role drift, duplicate kaam |
| Goal | Team ko kya deliver karna hai? | Agents alag disha mein bhaagte hain |
| Shared vs private context | Kisko kitna dikhna chahiye? | Context bleeding, cost blow-up |
| Coordination | Next step kaun decide karta hai? | Chaos ya bottleneck |
| Termination | Kab "done" hai? | Infinite ping-pong, bill 💸 |

## Topologies ka map

```
 SEQUENTIAL (02)          SUPERVISOR (03)            HIERARCHICAL (04)
 A ─► B ─► C ─► D             ┌─S─┐                       M
 (fixed order)             ┌──┼──┼──┐                 ┌───┴───┐
                           A  B  C                   L1      L2
                         (central router)           ┌┴┐     ┌┴┐
                                                    w w     w w

 GROUP CHAT (05)          DEBATE / JURY (06)         SWARM (07)
 ┌──────────────┐          PRO ⇄ CON                  A ──► B
 │ shared room  │             │                       ▲     │
 │ A  B  C  D   │           JUDGE(s)                  │     ▼
 └──────────────┘         (adversarial)               D ◄── C
 (selector picks speaker)                            (peer handoffs)
```

## Projects (is order mein padho)

| # | Project | Topology | Example | Key concepts |
|---|---|---|---|---|
| 01 | [role-design-basics](01-role-design-basics/) | 2 roles | Writer + Editor | Role anatomy, prompt template, output contract, anti-patterns |
| 02 | [sequential-crew](02-sequential-crew/) | Pipeline | PM → Architect → Dev → QA | Role vs Task, context passing, bounded rework |
| 03 | [supervisor-team](03-supervisor-team/) | Central router | Research team | JSON routing, shared board vs private context, 3 termination guards |
| 04 | [hierarchical-teams](04-hierarchical-teams/) | Tree | Product launch | Decomposition, roll-up, span of control, hallucinated-name guard |
| 05 | [group-chat](05-group-chat/) | Shared room | Trip planning | Speaker selection (round-robin/rules/LLM), consensus termination |
| 06 | [debate-and-judge](06-debate-and-judge/) | Adversarial | Motion debate | Rubric judge, jury, self-consistency, mixture-of-agents |
| 07 | [swarm-handoffs](07-swarm-handoffs/) | Peer mesh | Customer support | Handoff-as-tool, context variables, ping-pong guard |

Har project mein:
- `CONCEPTS.md`: concept Hinglish mein, diagrams ke saath, aur "is project mein kaise use ho raha hai"
- `TESTING.md`: kaise chalayein, tests, traces mein kya dekhein, tinker exercises
- `main.py --offline`: bina API key ke chalta hai (role-aware fake LLM)
- `test_*.py`: offline tests (`pytest 06-multi-agent-systems`)

## Multi-LLM teams

Har project mein `llm_for(role)` hai: pehle `LLM_MODEL_<ROLE>` env dekhta hai, na mile to `LLM_MODEL`.

```bash
LLM_MODEL=groq:llama-3.1-8b-instant            # sab workers: sasta + fast
LLM_MODEL_SUPERVISOR=anthropic:claude-sonnet-5 # routing/judging: strong
LLM_MODEL_JUDGE2=gemini:gemini-2.5-flash       # jury mein alag provider = kam bias
```

Rule of thumb: **planning, routing aur judging ke liye strong model; bulk generation ke liye sasta model.**

## Kaunsa pattern kab?

```
Kaam ka order pehle se pata hai?  ── haan ──► SEQUENTIAL (02)
        │ nahi
        ▼
Workers 5 se zyada / alag domains? ── haan ──► HIERARCHICAL (04)
        │ nahi
        ▼
Conversation-style routing (support)? ── haan ──► SWARM (07)
        │ nahi
        ▼
Multiple perspectives / negotiation? ── haan ──► GROUP CHAT (05) / DEBATE (06)
        │ nahi
        ▼
                SUPERVISOR (03)
```

Aur sabse pehle yeh poochho: **kya ek hi agent + achhe tools kaafi hai?** Multi-agent = zyada cost, latency, aur debugging. Zaroorat ho tabhi use karo.

## Popular frameworks se mapping

| Is repo mein | CrewAI | AutoGen / AG2 | LangGraph | OpenAI Agents SDK |
|---|---|---|---|---|
| `Role` (01, 02) | `Agent(role, goal, backstory)` | `AssistantAgent(system_message)` | node + prompt | `Agent(instructions)` |
| `Task` + context (02) | `Task(description, expected_output, context=[...])` | — | state keys | — |
| Sequential crew (02) | `Process.sequential` | `SequentialChat` / nested chats | linear graph edges | chained runs |
| Supervisor (03) | `Process.hierarchical` (manager_llm) | `SelectorGroupChat` | `langgraph-supervisor` | orchestrator agent + agents-as-tools |
| Hierarchical (04) | hierarchical crew with sub-crews | nested group chats | subgraphs | agents-as-tools nested |
| Group chat (05) | — | `GroupChat` + `GroupChatManager`, `RoundRobinGroupChat` | shared-state loop | — |
| Debate / jury (06) | — | multi-agent debate examples | parallel branches + judge node | parallel runs + judge |
| Swarm handoffs (07) | — | `Swarm` team (handoffs) | `langgraph-swarm` | `handoffs=[...]` (native) |

Frameworks yeh sab ready-made dete hain. Yahan hum from scratch bana rahe hain taaki andar ka mechanism samajh aaye. Framework use karte waqt bhi yahi concepts (roles, context, termination) debug karne padte hain.

## Communication mechanisms?

Agents **kaise** messages bhejte hain (in-process calls, shared blackboard, pub/sub, HTTP, **MCP**, **A2A**) woh **section 05 · agent-communication** mein hai. Yeh section **organisation** pe focus karta hai: kaun kya karega aur kaun kisko report karega.

## Run everything

```bash
pytest 06-multi-agent-systems -v

export AGENT_VERBOSE=0
for p in 01-role-design-basics 02-sequential-crew 03-supervisor-team 04-hierarchical-teams 05-group-chat; do
  python 06-multi-agent-systems/$p/main.py --offline
done
python 06-multi-agent-systems/06-debate-and-judge/main.py debate "Remote work wins" --judges 3 --offline
python 06-multi-agent-systems/07-swarm-handoffs/main.py --offline --once "I want a refund for order A100"
```
