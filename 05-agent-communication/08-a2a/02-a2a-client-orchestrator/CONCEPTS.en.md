**Language:** [Hinglish](CONCEPTS.md) · English

# A2A Client + Orchestrator: concepts

## What the client does
An A2A client (or "client agent") is the one that **delegates** work. Its jobs:
1. **Discovery**: find agents and read their cards
2. **Selection**: pick the right agent and skill for the job
3. **Delegation**: send `message/send` / `message/stream`
4. **Conversation management**: answer when `input-required` comes back (same `taskId`)
5. **Result handling**: extract artifacts (text + data), handle errors/failed states

```
                        ┌───────────────── Orchestrator ─────────────────┐
 user: "convert 250 USD"│                                                │
 ──────────────────────►│ 1. registry.summary()  (skills from cards)     │
                        │ 2. LLM/router: best = "Travel & Currency Expert"│
                        │ 3. send_to_agent(best, "convert 250 USD") ──────┼──► Travel agent
                        │    ◄── {state: input-required,                  │◄── Task(input-required)
                        │         question: "Which currency?"}            │
                        │ 4. ask_user("Which currency?") ──► human: "INR" │
                        │ 5. send_to_agent(best, "INR", task_id=T1) ──────┼──► same task continues
                        │    ◄── {state: completed, answer, data}         │◄── Task(completed + artifact)
 ◄──────────────────────│ 6. final combined answer                        │
                        └─────────────────────────────────────────────────┘
```

## Ways to discover (subtypes)
| Way | How | When |
|---|---|---|
| **Well-known URI** (this project) | You know the domain → `GET https://agent.example.com/.well-known/agent.json` | You know which agents exist |
| **Registry / catalog** | A central service where cards are registered, and you search by skill/tag | A large org, lots of agents |
| **Direct config** | The card JSON sits in a config file, or arrives through a private channel | Private/internal agents |

`AgentRegistry` here is a small in-memory catalog: URLs → cards → lookup by name.

## Selection: how do you pick an agent?
**1. Rule/keyword router (`SkillRouter`)**: matches the words in the query against the skill's tags, name and examples.
- ✅ Cheap, deterministic, testable, no LLM cost
- ❌ Doesn't understand synonyms ("forex" ≠ "currency" unless it is a tag)

**2. LLM orchestrator (`build_orchestrator_agent`)**: the LLM gets a summary of the cards through a tool (`list_remote_agents`), and picks on its own.
- ✅ Smart, can combine several agents, handles follow-up questions
- ❌ Expensive, non-deterministic, can also pick the wrong agent

**3. Hybrid (common in production)**: the router picks the top-3 candidates, then the LLM makes the final choice among them. Skill matching with embeddings is another option (see the RAG section).

## The orchestrator LLM's tools
```
list_remote_agents()                      -> [{name, description, skills[{id, tags}], streaming}]
send_to_agent(agent_name, message, task_id="")  -> {"state", "task_id", "answer"|"question", "data"?}
ask_user(question)                        -> the human's answer
```
Note: **we do not give the LLM the remote agent's whole Task**. We give only the needed fields (state,
answer/question, data). This saves tokens and keeps the LLM from getting confused. This is "tool result
shaping".

## Handling input-required: 3 options
1. **The orchestrator answers itself**: if the answer is already in the earlier conversation ("I already said INR").
2. **Ask the human**: the `ask_user` tool or `delegate(..., ask_human=input)`.
3. **Ask another agent**: e.g. get the home currency from a user profile agent.

`delegate()` has a `max_turns` guard. If the remote agent keeps asking questions, it will not become an infinite loop.

## Sync vs Stream vs Poll (client side)
```
send (blocking)       client ──req──► ... wait ... ◄──Task (final)          simple
stream (SSE)          client ──req──► ◄─ev ◄─ev ◄─ev ◄─final               live UI / progress
send(blocking=False)  client ──req──► ◄─Task(working)                       long job
  + wait()            client ──tasks/get──► ◄─working ... ──tasks/get──► ◄─completed
```
The client should **respect the card's capabilities**: `A2AClient.stream()` first checks
`card.capabilities.streaming`. If streaming is not supported, it does not even try
to stream (the packing agent in 03 is an example of this).

## Errors & failure modes
| Situation | What the client should do |
|---|---|
| 401 | look at the card's `securitySchemes`, get a credential and retry |
| JSON-RPC error (-32001 etc.) | raise `A2AError(code, message)`, give the orchestrator LLM an `ERROR: ...` text |
| `failed` task | the reason is in status.message. Retry or try another agent |
| Agent down / timeout | remove the agent from the registry, use a fallback agent |
| The remote agent's answer | is **untrusted text**, so add a prompt-injection guard |

## Which pattern when
- 1-2 fixed agents, predictable work → **SkillRouter + delegate** (no LLM)
- Free-form user requests, many agents → **LLM orchestrator**
- Long research-style tasks → **non-blocking + polling** (or push notifications)
- Chat UI → **streaming**

## How this project uses it
| Concept | Where |
|---|---|
| Card discovery (v0.3 path, then v0.2 fallback) | `a2a_client.py` → `A2AClient.card` |
| send / stream (SSE parse) / get / cancel / wait(poll) | `A2AClient` methods |
| Building a Text + DataPart message | `A2AClient.build_message` |
| Extracting the answer/data from an artifact | `task_answer()`, `task_data()` |
| Registry / catalog | `a2a_orchestrator.py` → `AgentRegistry` |
| No-LLM skill routing | `SkillRouter.rank/pick` |
| input-required loop with human | `delegate()` |
| Streaming delegate | `delegate_streaming()` |
| LLM orchestrator + tools | `build_orchestrator_agent()` |
| Offline fake orchestrator brain | `offline_orchestrator_llm()` |
| Testing without network (TestClient = httpx.Client) | `test_a2a_orchestrator.py` → `http` fixture |
