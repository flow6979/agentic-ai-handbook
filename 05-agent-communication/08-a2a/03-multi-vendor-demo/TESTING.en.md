**Language:** [Hinglish](TESTING.md) · English

# Multi-vendor A2A: how to test and tinker

## Setup
```bash
source .venv/bin/activate && pip install -e ".[all]"
cd 05-agent-communication/08-a2a/03-multi-vendor-demo
```

## 1. Offline (no key)
```bash
python main.py --offline                                   # Tokyo, January, 5 days, 500 USD -> JPY
python main.py --offline --city Goa --month 7 --days 4 --budget 300 --home USD --local INR
python main.py --offline --llm-orchestrator "what should I pack for my london trip in december for 3 days"
```
Look at "Agents used" in the output: which sub-task was done by which vendor's agent.

## 2. Real LLMs, different providers
```bash
# put keys for both providers in .env
LLM_MODEL_A=groq:llama-3.3-70b-versatile LLM_MODEL_B=gemini:gemini-3.8-flash python main.py
```
This starts both servers in this same process on real ports **9001** and **9002**, then orchestrates.
While it runs you can check from another terminal:
```bash
curl -s localhost:9002/.well-known/agent.json | python -m json.tool     # vendor 2's card
```

## 3. Three terminals (the most realistic)
```bash
# T1: vendor 1
python ../01-a2a-server/main.py --port 9001            # real LLM (or --offline)
# T2: vendor 2
python a2a_packing_agent_raw.py --port 9002
# T3: orchestrator
python main.py --agents http://127.0.0.1:9001 http://127.0.0.1:9002
python main.py --agents http://127.0.0.1:9001 http://127.0.0.1:9002 "Plan Paris in December for 4 days with 800 EUR"
```
Now stop T2 (Ctrl+C) and run T3 again. What happens? (See tinker #1 below.)

## 4. Talk to vendor 2 with curl
```bash
curl -s -X POST localhost:9002/ -H 'content-type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"message/send","params":{"message":{"kind":"message","role":"user","messageId":"x","parts":[{"kind":"data","data":{"city":"Tokyo","month":7,"days":3}}]}}}' | python -m json.tool
curl -s -X POST localhost:9002/ -H 'content-type: application/json' -d '{"jsonrpc":"2.0","id":2,"method":"message/stream","params":{}}'   # -32004 streaming not supported
```

## 5. Offline tests
```bash
# repo root
.venv/bin/pytest 05-agent-communication/08-a2a/03-multi-vendor-demo -v
```
- `test_raw_agent_is_spec_shaped`: the hand-written server's output is validated against our pydantic models (wire compatibility)
- `test_client_respects_streaming_capability`
- `test_plan_trip_fans_out_to_both_vendors`
- `test_llm_orchestrator_picks_packing_vendor`
- `test_over_real_network`: 2 real uvicorn servers on random ports

## Tinker with it
1. **Graceful degradation**: wrap each future in `plan_trip` in a `try/except`. If the packing agent is down, write "packing unavailable" in the plan instead of crashing.
2. **A third vendor**: build a "Weather agent" (Node/Express, Go, or any language) that speaks the same JSON-RPC. Add its URL to the registry. The Python orchestrator will use it without any change. That is the proof of interoperability.
3. **Official SDK**: `pip install a2a-sdk` and rewrite the packing agent with the SDK's `AgentExecutor` + `A2AStarletteApplication`. The tests (which only check the wire) should still pass.
4. **Add streaming support** to the packing agent (`message/stream` → SSE, `streaming: true` in the card). Then have the orchestrator use `delegate_streaming`.
5. **Semantic mismatch**: send the packing agent text only (remove the DataPart) and try inputs like "Tokyo in jul". Where does parsing go wrong? This shows why structured parts matter.
6. **Cost split**: print the `usage` tokens of the two LLMs separately (travel agent vs orchestrator) and see which one spends more.
