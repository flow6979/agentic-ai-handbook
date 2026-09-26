**Language:** Hinglish · [English](TESTING.en.md)

# 05 · Group Chat — Test & Tinker

## Run

```bash
# teeno selectors offline compare karo
python 06-multi-agent-systems/05-group-chat/main.py --offline --selector round_robin
python 06-multi-agent-systems/05-group-chat/main.py --offline --selector rules
python 06-multi-agent-systems/05-group-chat/main.py --offline --selector llm

# real LLM
python 06-multi-agent-systems/05-group-chat/main.py "Plan a 2-day Jaipur trip under INR 15,000" --selector llm --max-turns 8
```

Expected (offline): transcript print hoga, aur end mein `[stopped: consensus after 6 turns ...]` (rules selector ke saath 7 turns, kyunki `@planner` mention order badal deta hai).

## Tests

```bash
pytest 06-multi-agent-systems/05-group-chat -v
```

| Test | Kya prove karta hai |
|---|---|
| `test_llm_selector_reaches_consensus` | LLM selector ka flow, consensus termination |
| `test_round_robin_order` | Fixed order |
| `test_rule_based_mention_and_keywords` | `@mention` > keywords > fallback (last speaker skip) |
| `test_llm_selector_falls_back_on_invalid_name` | Hallucinated speaker → round-robin fallback |
| `test_terminate_keyword_and_max_turns` | Dono termination paths |
| `test_every_participant_sees_shared_transcript` | Shared context sach mein shared hai |

## Traces mein kya dekhna hai

`[groupchat:llm] budget_keeper: ...` lines mein turn number hai. Real LLM pe dekho:
- Kya consensus sach mein aata hai, ya `max_turns` pe katta hai?
- LLM selector kisi ek ko zyada to nahi chun raha?

## Tinker karo 🔧

1. **Devil's advocate**: ek `skeptic` participant add karo jo hamesha risk dhundhe. Kya consensus late hota hai? Kya plan better hota hai?
2. **Sliding window**: `Participant.speak()` mein sirf last 6 messages bhejo aur token usage compare karo.
3. **Random selector** likho, aur **fairness rule** daalo (koi 2 baar lagatar na bole).
4. **Human in the chat**: ek `Participant` banao jiska `speak()` `input()` se aata hai. Ab tum bhi group mein ho!
5. **Consensus vs keyword**: planner prompt mein "say TERMINATE when final" daalo. Kaunsa pehle trigger hota hai?
6. **Mixed models**: planner = bada model, baaki = chhota model. Transcript ki quality compare karo.
