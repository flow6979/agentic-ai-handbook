**Language:** Hinglish · [English](CONCEPTS.en.md)

# 05 · Group Chat — Sab ek room mein baat karte hain

## Seedhi baat

Ek WhatsApp group socho jisme Planner, Budget Keeper aur Local Guide hain. Sab **ek hi conversation** dekhte hain aur baari baari bolte hain. Koi ek "boss" task assign nahi karta. Bas yeh decide karna hota hai ki **agla kaun bolega** aur **kab baat khatam hogi**. Microsoft AutoGen ka `GroupChat` isi idea pe bana hai.

```
                ┌────────────────────────────────────────┐
                │        SHARED TRANSCRIPT (sab dekhte)   │
                │ user: 3 din Goa, 30k budget            │
                │ planner: Day1 beaches... hotel 12k     │
                │ budget_keeper: 35k! 5k over @planner   │
                │ local_guide: fish thali try karo       │
                │ planner: homestay 7k. AGREE            │
                └───────────────┬────────────────────────┘
                     ▲          │
       naya message  │          │  "agla kaun?"
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
repeat (max_turns tak):
    speaker = selector.next(transcript)
    msg     = speaker.speak(transcript)   ← poora transcript dekh ke
    transcript.append(msg)
    if "TERMINATE" in msg      → stop (terminate)
    if sab ka latest = "AGREE" → stop (consensus)
```

## Speaker selection strategies (subtypes)

| Strategy | Kaise | ✅ | ❌ | Code |
|---|---|---|---|---|
| **Round-robin** | Baari baari, fixed order | Free, predictable | Irrelevant log bhi bolte hain | `RoundRobinSelector` |
| **Rule-based** | `@name` mention → woh; keywords ("cost", "budget") → budget_keeper; warna round-robin (last speaker skip) | Free, deterministic, debuggable | Rules maintain karne padte hain | `RuleBasedSelector` |
| **LLM-selected** | Manager LLM roster + recent chat dekh ke naam deta hai | Flexible, smart | Har turn extra LLM call (~2x cost) | `LLMSelector` |
| Random | Random participant | Brainstorming diversity | Chaotic | (exercise) |
| Manual / human | Human choose kare | Full control | Slow | (exercise) |

**LLMSelector ke safety nets**: sirf last 8 messages bhejta hai (cost control), aur invalid naam aaye (jaise "ceo") to round-robin pe fallback karta hai.

## Termination strategies

| Strategy | Kab | Risk |
|---|---|---|
| **Keyword** (`TERMINATE`) | Koi participant bole "done" | LLM bhool jaaye to kabhi band nahi hoga |
| **Consensus** (sab ka latest message `AGREE`) | Collaborative decision | Ek zid pe adaa rahe to kabhi nahi hoga |
| **max_turns** | Hamesha, as a safety net | Beech mein kat sakta hai |
| Judge/LLM check | Ek LLM decide kare "goal achieved?" | Extra cost |

Rule: **hamesha `max_turns` rakho**, chahe koi aur strategy bhi ho.

## Group chat vs Supervisor

| | Supervisor (03) | Group chat (05) |
|---|---|---|
| Context | Workers ko private slices milte hain | **Sab ko poora transcript** |
| Control | Manager task + instruction deta hai | Selector sirf "kaun bolega" chunta hai |
| Achha kis ke liye | Clear task decomposition | Brainstorming, negotiation, multiple perspectives |
| Cost | Moderate | Transcript har turn badhta hai, cost quadratic-ish badhti hai |

## Pitfalls
1. **Context growth**: har turn poora transcript jaata hai, isliye turns × length = tokens. Fix: summarize old turns, sliding window.
2. **Echo chamber**: sab ek doosre se sehmat ho jaate hain bina critique ke. Fix: ek devil's advocate role rakho.
3. **Dominant speaker**: LLM selector ek hi agent ko baar baar chune. Fix: last speaker skip + fairness rule.
4. **Role drift**: lambi chat mein budget_keeper itinerary banane lagta hai. Fix: role prompt har turn system prompt mein rahe (hum yahi karte hain).
5. **No termination**: `max_turns` hamesha rakho.

## Is project mein kaise use ho raha hai

| Concept | File / function |
|---|---|
| Shared transcript | `group_chat.py` → `ChatMessage`, `GroupChat.run()` ka `transcript` |
| Participant = role + LLM | `Participant.speak()` (poora transcript prompt mein) |
| Round-robin | `RoundRobinSelector` |
| Rule-based (@mention + keywords) | `RuleBasedSelector`, `TRIP_RULES` |
| LLM-selected + fallback | `LLMSelector` (`NextSpeaker` schema) |
| Keyword / consensus / max_turns | `GroupChat.run()`, `_consensus()` |
| Per-participant models | `trip_team(llm_factory)` → `llm_for("planner")`... |
