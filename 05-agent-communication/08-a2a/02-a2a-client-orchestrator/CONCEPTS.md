**Language:** Hinglish · [English](CONCEPTS.en.md)

# A2A Client + Orchestrator: concepts

## Client ke kaam
A2A client (ya "client agent") woh hai jo kaam **delegate** karta hai. Uske kaam:
1. **Discovery**: agents dhoondhna aur unke cards padhna
2. **Selection**: kaam ke hisaab se sahi agent aur skill chunna
3. **Delegation**: `message/send` / `message/stream` bhejna
4. **Conversation management**: `input-required` aane pe jawab dena (same `taskId`)
5. **Result handling**: artifacts (text + data) nikaalna, errors/failed states handle karna

```
                        ┌───────────────── Orchestrator ─────────────────┐
 user: "convert 250 USD"│                                                │
 ──────────────────────►│ 1. registry.summary()  (cards se skills)       │
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

## Discovery ke tareeke (subtypes)
| Tareeka | Kaise | Kab |
|---|---|---|
| **Well-known URI** (yeh project) | Domain pata hai → `GET https://agent.example.com/.well-known/agent.json` | Pata hai kaun se agents hain |
| **Registry / catalog** | Central service jahan cards register hote hain, aur tum skill/tag se search karte ho | Badi org, bahut saare agents |
| **Direct config** | Card JSON config file mein ho, ya private channel se mile | Private/internal agents |

`AgentRegistry` yahan ek chhota in-memory catalog hai: URLs → cards → naam se lookup.

## Selection: agent kaise chunein?
**1. Rule/keyword router (`SkillRouter`)**: query ke words ko skill ke tags, name aur examples se match karta hai.
- ✅ Sasta, deterministic, testable, LLM ka koi kharcha nahi
- ❌ Synonyms nahi samajhta ("forex" ≠ "currency" jab tak tag mein na ho)

**2. LLM orchestrator (`build_orchestrator_agent`)**: LLM ko cards ka summary tool (`list_remote_agents`) ke through milta hai, aur woh khud chunta hai.
- ✅ Samajhdaar hai, kai agents ko combine kar sakta hai, follow-up sawaal handle karta hai
- ❌ Mehenga, non-deterministic, galat agent bhi chun sakta hai

**3. Hybrid (production mein common)**: router top-3 candidates nikaalta hai, phir LLM unme se final choose karta hai. Embeddings se skill matching bhi ek option hai (RAG section dekho).

## Orchestrator LLM ke tools
```
list_remote_agents()                      -> [{name, description, skills[{id, tags}], streaming}]
send_to_agent(agent_name, message, task_id="")  -> {"state", "task_id", "answer"|"question", "data"?}
ask_user(question)                        -> insaan ka jawab
```
Dhyaan do: **remote agent ka poora Task LLM ko nahi dete**. Sirf zaroori fields dete hain (state,
answer/question, data). Isse tokens bachte hain aur LLM confuse nahi hota. Yeh "tool result
shaping" hai.

## Input-required handling: 3 options
1. **Orchestrator khud jawab de**: agar jawab pehle ki conversation mein hai ("maine pehle hi INR bola tha").
2. **Human se poochho**: `ask_user` tool ya `delegate(..., ask_human=input)`.
3. **Doosre agent se poochho**: e.g. user profile agent se home currency le lo.

`delegate()` mein `max_turns` guard hai. Remote agent baar-baar sawaal poochhta rahe to infinite loop nahi banega.

## Sync vs Stream vs Poll (client side)
```
send (blocking)       client ──req──► ... wait ... ◄──Task (final)          simple
stream (SSE)          client ──req──► ◄─ev ◄─ev ◄─ev ◄─final               live UI / progress
send(blocking=False)  client ──req──► ◄─Task(working)                       lamba kaam
  + wait()            client ──tasks/get──► ◄─working ... ──tasks/get──► ◄─completed
```
Client ko **card ki capabilities respect karni chahiye**: `A2AClient.stream()` pehle
`card.capabilities.streaming` check karta hai. Streaming support nahi hai to stream karne ki
koshish hi nahi karta (03 ka packing agent iska example hai).

## Errors & failure modes
| Situation | Client ko kya karna chahiye |
|---|---|
| 401 | card ke `securitySchemes` dekho, credential lo aur retry karo |
| JSON-RPC error (-32001 etc.) | `A2AError(code, message)` raise karo, orchestrator LLM ko `ERROR: ...` text do |
| `failed` task | status.message mein reason hota hai. Retry karo ya doosra agent try karo |
| Agent down / timeout | registry se agent hatao, fallback agent use karo |
| Remote agent ka jawab | **untrusted text** hai, isliye prompt-injection guard lagao |

## Kab kaunsa pattern
- 1-2 fixed agents, predictable kaam → **SkillRouter + delegate** (bina LLM ke)
- Free-form user requests, kai agents → **LLM orchestrator**
- Lambe research-type tasks → **non-blocking + polling** (ya push notifications)
- Chat UI → **streaming**

## Is project mein kaise use ho raha hai
| Concept | Kahan |
|---|---|
| Card discovery (v0.3 path, phir v0.2 fallback) | `a2a_client.py` → `A2AClient.card` |
| send / stream (SSE parse) / get / cancel / wait(poll) | `A2AClient` methods |
| Text + DataPart message banana | `A2AClient.build_message` |
| Artifact se answer/data nikaalna | `task_answer()`, `task_data()` |
| Registry / catalog | `a2a_orchestrator.py` → `AgentRegistry` |
| No-LLM skill routing | `SkillRouter.rank/pick` |
| input-required loop with human | `delegate()` |
| Streaming delegate | `delegate_streaming()` |
| LLM orchestrator + tools | `build_orchestrator_agent()` |
| Offline fake orchestrator brain | `offline_orchestrator_llm()` |
| Testing without network (TestClient = httpx.Client) | `test_a2a_orchestrator.py` → `http` fixture |
