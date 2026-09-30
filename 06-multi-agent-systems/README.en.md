**Language:** [Hinglish](README.md) · English

# 06 · Multi-Agent Systems (with Roles)

> One agent = one LLM + tools + a loop. A **multi-agent system** = many agents, each with its own **role**, working together towards one goal.

## What is a multi-agent system made of?

```
┌───────────────────────────────────────────────────────────────────┐
│                       MULTI-AGENT SYSTEM                          │
│                                                                   │
│  1. ROLES        who is who (persona, goal, tools, rules)         │
│  2. GOAL         the whole team's shared objective                │
│  3. CONTEXT      shared (board/transcript) vs private (per-role)  │
│  4. COORDINATION who works next? (code / manager / peer)          │
│  5. TERMINATION  when to stop? (done / budget / guard)            │
│  6. COMMUNICATION how messages travel → section 05                │
└───────────────────────────────────────────────────────────────────┘
```

| Building block | Question | If it goes wrong |
|---|---|---|
| Roles | What is each agent responsible for? | Role drift, duplicated work |
| Goal | What does the team have to deliver? | Agents run in different directions |
| Shared vs private context | Who should see how much? | Context bleeding, cost blow-up |
| Coordination | Who decides the next step? | Chaos or a bottleneck |
| Termination | When is it "done"? | Infinite ping-pong, a big bill 💸 |

## Map of topologies

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

## Projects (read them in this order)

| # | Project | Topology | Example | Key concepts |
|---|---|---|---|---|
| 01 | [role-design-basics](01-role-design-basics/) | 2 roles | Writer + Editor | Role anatomy, prompt template, output contract, anti-patterns |
| 02 | [sequential-crew](02-sequential-crew/) | Pipeline | PM → Architect → Dev → QA | Role vs Task, context passing, bounded rework |
| 03 | [supervisor-team](03-supervisor-team/) | Central router | Research team | JSON routing, shared board vs private context, 3 termination guards |
| 04 | [hierarchical-teams](04-hierarchical-teams/) | Tree | Product launch | Decomposition, roll-up, span of control, hallucinated-name guard |
| 05 | [group-chat](05-group-chat/) | Shared room | Trip planning | Speaker selection (round-robin/rules/LLM), consensus termination |
| 06 | [debate-and-judge](06-debate-and-judge/) | Adversarial | Motion debate | Rubric judge, jury, self-consistency, mixture-of-agents |
| 07 | [swarm-handoffs](07-swarm-handoffs/) | Peer mesh | Customer support | Handoff-as-tool, context variables, ping-pong guard |

Every project has:
- `CONCEPTS.md` / `CONCEPTS.en.md`: the concept with diagrams, plus "how this project uses it"
- `TESTING.md` / `TESTING.en.md`: how to run it, the tests, what to look for in traces, tinker exercises
- `main.py --offline`: runs without an API key (role-aware fake LLM)
- `test_*.py`: offline tests (`pytest 06-multi-agent-systems`)

## Multi-LLM teams

Every project has `llm_for(role)`: it first checks the `LLM_MODEL_<ROLE>` env var, and falls back to `LLM_MODEL` if it is not set.

```bash
LLM_MODEL=groq:llama-3.1-8b-instant            # all workers: cheap + fast
LLM_MODEL_SUPERVISOR=anthropic:claude-sonnet-5 # routing/judging: strong
LLM_MODEL_JUDGE2=gemini:gemini-3.8-flash       # a different provider in the jury = less bias
```

Rule of thumb: **use a strong model for planning, routing and judging; use a cheap model for bulk generation.**

## Which pattern when?

```
Is the order of work known up front?  ── yes ──► SEQUENTIAL (02)
        │ no
        ▼
More than 5 workers / different domains? ── yes ──► HIERARCHICAL (04)
        │ no
        ▼
Conversation-style routing (support)? ── yes ──► SWARM (07)
        │ no
        ▼
Multiple perspectives / negotiation? ── yes ──► GROUP CHAT (05) / DEBATE (06)
        │ no
        ▼
                SUPERVISOR (03)
```

And ask this first of all: **is a single agent with good tools enough?** Multi-agent means more cost, more latency and harder debugging. Use it only when you actually need it.

## Mapping to popular frameworks

| In this repo | CrewAI | AutoGen / AG2 | LangGraph | OpenAI Agents SDK |
|---|---|---|---|---|
| `Role` (01, 02) | `Agent(role, goal, backstory)` | `AssistantAgent(system_message)` | node + prompt | `Agent(instructions)` |
| `Task` + context (02) | `Task(description, expected_output, context=[...])` | - | state keys | - |
| Sequential crew (02) | `Process.sequential` | `SequentialChat` / nested chats | linear graph edges | chained runs |
| Supervisor (03) | `Process.hierarchical` (manager_llm) | `SelectorGroupChat` | `langgraph-supervisor` | orchestrator agent + agents-as-tools |
| Hierarchical (04) | hierarchical crew with sub-crews | nested group chats | subgraphs | agents-as-tools nested |
| Group chat (05) | - | `GroupChat` + `GroupChatManager`, `RoundRobinGroupChat` | shared-state loop | - |
| Debate / jury (06) | - | multi-agent debate examples | parallel branches + judge node | parallel runs + judge |
| Swarm handoffs (07) | - | `Swarm` team (handoffs) | `langgraph-swarm` | `handoffs=[...]` (native) |

Frameworks give you all of this ready-made. Here we build it from scratch so the mechanism underneath makes sense. Even when you use a framework, these are the same concepts (roles, context, termination) you end up debugging.

## Communication mechanisms?

**How** agents send messages (in-process calls, shared blackboard, pub/sub, HTTP, **MCP**, **A2A**) is covered in **section 05 · agent-communication**. This section focuses on **organisation**: who does what and who reports to whom.

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
