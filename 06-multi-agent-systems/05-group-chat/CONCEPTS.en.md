**Language:** [Hinglish](CONCEPTS.md) · English

# 05 · Group Chat: everyone talks in one room

## The short version

Picture a WhatsApp group with a Planner, a Budget Keeper and a Local Guide. Everyone sees **the same conversation** and they take turns speaking. No single "boss" assigns tasks. The only things to decide are **who speaks next** and **when the conversation ends**. Microsoft AutoGen's `GroupChat` is built on this idea.

```
                ┌────────────────────────────────────────┐
                │     SHARED TRANSCRIPT (everyone sees)   │
                │ user: 3 days Goa, 30k budget           │
                │ planner: Day1 beaches... hotel 12k     │
                │ budget_keeper: 35k! 5k over @planner   │
                │ local_guide: try the fish thali        │
                │ planner: homestay 7k. AGREE            │
                └───────────────┬────────────────────────┘
                     ▲          │
       new message   │          │  "who's next?"
                     │          ▼
                     │   ┌──────────────┐
                     │   │   SELECTOR   │  round-robin | rules | LLM
                     │   └──────┬───────┘
                     │          ▼
               [planner]  [budget_keeper]  [local_guide]
```

## Loop

```
transcript = [user task]
repeat (up to max_turns):
    speaker = selector.next(transcript)
    msg     = speaker.speak(transcript)   ← after reading the whole transcript
    transcript.append(msg)
    if "TERMINATE" in msg             → stop (terminate)
    if everyone's latest = "AGREE"    → stop (consensus)
```

## Speaker selection strategies (subtypes)

| Strategy | How | ✅ | ❌ | Code |
|---|---|---|---|---|
| **Round-robin** | Take turns in a fixed order | Free, predictable | Irrelevant participants speak too | `RoundRobinSelector` |
| **Rule-based** | `@name` mention → that one; keywords ("cost", "budget") → budget_keeper; otherwise round-robin (skip the last speaker) | Free, deterministic, debuggable | The rules need maintaining | `RuleBasedSelector` |
| **LLM-selected** | A manager LLM looks at the roster + recent chat and returns a name | Flexible, smart | An extra LLM call every turn (~2x cost) | `LLMSelector` |
| Random | A random participant | Diversity for brainstorming | Chaotic | (exercise) |
| Manual / human | A human chooses | Full control | Slow | (exercise) |

**LLMSelector's safety nets**: it sends only the last 8 messages (cost control), and if an invalid name comes back (like "ceo") it falls back to round-robin.

## Termination strategies

| Strategy | When | Risk |
|---|---|---|
| **Keyword** (`TERMINATE`) | A participant says "done" | If the LLM forgets, it never stops |
| **Consensus** (everyone's latest message is `AGREE`) | Collaborative decisions | If one participant digs in, it never happens |
| **max_turns** | Always, as a safety net | May cut the chat off midway |
| Judge/LLM check | An LLM decides "goal achieved?" | Extra cost |

Rule: **always keep `max_turns`**, even if you have another strategy too.

## Group chat vs Supervisor

| | Supervisor (03) | Group chat (05) |
|---|---|---|
| Context | Workers get private slices | **Everyone gets the whole transcript** |
| Control | The manager gives a task + instruction | The selector only picks "who speaks" |
| Good for | Clear task decomposition | Brainstorming, negotiation, multiple perspectives |
| Cost | Moderate | The transcript grows every turn, so cost grows roughly quadratically |

## Pitfalls
1. **Context growth**: the whole transcript goes out every turn, so turns × length = tokens. Fix: summarize old turns, use a sliding window.
2. **Echo chamber**: everyone agrees with everyone without any critique. Fix: add a devil's advocate role.
3. **Dominant speaker**: the LLM selector keeps picking the same agent. Fix: skip the last speaker + a fairness rule.
4. **Role drift**: in a long chat the budget_keeper starts building the itinerary. Fix: keep the role prompt in the system prompt on every turn (which is what we do).
5. **No termination**: always keep `max_turns`.

## How this project uses it

| Concept | File / function |
|---|---|
| Shared transcript | `group_chat.py` → `ChatMessage`, the `transcript` in `GroupChat.run()` |
| Participant = role + LLM | `Participant.speak()` (the whole transcript goes in the prompt) |
| Round-robin | `RoundRobinSelector` |
| Rule-based (@mention + keywords) | `RuleBasedSelector`, `TRIP_RULES` |
| LLM-selected + fallback | `LLMSelector` (`NextSpeaker` schema) |
| Keyword / consensus / max_turns | `GroupChat.run()`, `_consensus()` |
| Per-participant models | `trip_team(llm_factory)` → `llm_for("planner")`... |
