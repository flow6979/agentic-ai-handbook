**Language:** Hinglish · [English](TESTING.en.md)

# Testing: workflows vs agents demo

## Setup (repo root se, ek baar)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
cp .env.example .env      # ek provider ki key bharo, e.g. LLM_MODEL=groq:llama-3.3-70b-versatile
```

## Run

```bash
# bina key ke (scripted fake LLM):
python 02-agentic-architectures/00-workflows-vs-agents/main.py --offline

# real LLM ke saath:
python 02-agentic-architectures/00-workflows-vs-agents/main.py
python 02-agentic-architectures/00-workflows-vs-agents/main.py --user u2
```

## Kya dekhna hai

```
=== 1) WORKFLOW ===
{'subtotal': 4097.0, 'tax': 737.46, 'total': 4834.46}   <- code ne calculate kiya
...
LLM calls: 1

=== 2) AGENT ===
[cart-agent:tool] get_cart({'user_id': 'u1'})           <- LLM ne khud tool chuna
[cart-agent:tool] compute_total({'subtotal': 4097.0})
...
LLM calls: 3  tokens: Usage(...)
```

- Workflow mein total **hamesha** same aur sahi hoga.
- Agent mode (real LLM) mein dekho: kya model ne `compute_total` call kiya ya khud math kar diya? System prompt mana karta hai, lekin models kabhi kabhi ignore karte hain. Yahi "kam predictability" hai.
- Token count compare karo: agent har step pe poori history dobara bhejta hai.

## Offline tests

```bash
pytest 02-agentic-architectures/00-workflows-vs-agents -v
```

- `test_chain_does_math_in_code_and_calls_llm_once`: chain = 1 LLM call, numbers prompt mein pass hue.
- `test_agent_decides_tool_order_itself`: agent ne `get_cart` -> `compute_total` order chuna.
- `test_agent_recovers_from_bad_user_id`: tool error crash nahi karta, model ko wapas jaata hai.

## Tinker karo

1. **Naya sawaal**: agent se poochho *"u1 aur u2 dono ke carts ka combined total?"*. Chain yeh nahi kar sakti bina code badle; agent kar lega. Yahi flexibility hai.
2. **Coupon tool add karo**: `apply_coupon(code) -> discount%` tool banao. Chain mein naya step likhna padega; agent mein sirf tools list mein add karo. Dono ka code diff compare karo.
3. **System prompt hatao**: "Never do tax math yourself" line hata ke real LLM pe 5 baar chalao. Kitni baar model ne khud (galat?) math kiya?
4. **max_steps=1** set karo agent mein: kya hota hai? (`stopped_reason` dekho)
5. **Cost measure karo**: `AGENT_TRACE_FILE=trace.jsonl` set karke dono chalao aur tokens compare karo.
