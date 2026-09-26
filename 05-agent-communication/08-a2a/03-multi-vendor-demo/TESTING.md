**Language:** Hinglish · [English](TESTING.en.md)

# Multi-vendor A2A: test aur tinker kaise karein

## Setup
```bash
source .venv/bin/activate && pip install -e ".[all]"
cd 05-agent-communication/08-a2a/03-multi-vendor-demo
```

## 1. Offline (koi key nahi)
```bash
python main.py --offline                                   # Tokyo, January, 5 days, 500 USD -> JPY
python main.py --offline --city Goa --month 7 --days 4 --budget 300 --home USD --local INR
python main.py --offline --llm-orchestrator "what should I pack for my london trip in december for 3 days"
```
Output mein "Agents used" dekho: kaunsa sub-task kis vendor ke agent ne kiya.

## 2. Real LLMs, alag providers
```bash
# .env mein dono providers ki keys daalo
LLM_MODEL_A=groq:llama-3.3-70b-versatile LLM_MODEL_B=gemini:gemini-2.5-flash python main.py
```
Yeh dono servers ko isi process mein real ports **9001** aur **9002** pe start karta hai, phir orchestrate karta hai.
Chalte waqt doosre terminal se check kar sakte ho:
```bash
curl -s localhost:9002/.well-known/agent.json | python -m json.tool     # vendor 2 ka card
```

## 3. Teen terminals (sabse realistic)
```bash
# T1: vendor 1
python ../01-a2a-server/main.py --port 9001            # real LLM (ya --offline)
# T2: vendor 2
python a2a_packing_agent_raw.py --port 9002
# T3: orchestrator
python main.py --agents http://127.0.0.1:9001 http://127.0.0.1:9002
python main.py --agents http://127.0.0.1:9001 http://127.0.0.1:9002 "Plan Paris in December for 4 days with 800 EUR"
```
Ab T2 band karo (Ctrl+C) aur T3 phir chalao. Kya hota hai? (Neeche tinker #1 dekho.)

## 4. Vendor 2 se curl pe baat
```bash
curl -s -X POST localhost:9002/ -H 'content-type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"message/send","params":{"message":{"kind":"message","role":"user","messageId":"x","parts":[{"kind":"data","data":{"city":"Tokyo","month":7,"days":3}}]}}}' | python -m json.tool
curl -s -X POST localhost:9002/ -H 'content-type: application/json' -d '{"jsonrpc":"2.0","id":2,"method":"message/stream","params":{}}'   # -32004 streaming not supported
```

## 5. Offline tests
```bash
# repo root
.venv/bin/pytest 05-agent-communication/08-a2a/03-multi-vendor-demo -v
```
- `test_raw_agent_is_spec_shaped`: hand-written server ka output hamare pydantic models se validate hota hai (wire compatibility)
- `test_client_respects_streaming_capability`
- `test_plan_trip_fans_out_to_both_vendors`
- `test_llm_orchestrator_picks_packing_vendor`
- `test_over_real_network`: 2 asli uvicorn servers random ports pe

## Tinker karo
1. **Graceful degradation**: `plan_trip` mein har future ko `try/except` mein daalo. Packing agent down ho to plan mein "packing unavailable" likho, crash mat karo.
2. **Teesra vendor**: ek "Weather agent" banao (Node/Express, Go, ya koi bhi language) jo same JSON-RPC bole. Registry mein URL jodo. Python orchestrator bina change ke usse use karega. Yahi interoperability ka proof hai.
3. **Official SDK**: `pip install a2a-sdk` karke packing agent ko SDK ke `AgentExecutor` + `A2AStarletteApplication` se dobara likho. Tests (jo sirf wire check karte hain) pass hone chahiye.
4. **Streaming support jodo** packing agent mein (`message/stream` → SSE, card mein `streaming: true`). Phir orchestrator `delegate_streaming` use kare.
5. **Semantic mismatch**: packing agent ko sirf text bhejo (DataPart hata do) aur "Tokyo in jul" jaise inputs try karo. Kahan galat parse hota hai? Isse samajh aata hai ki structured parts kyun zaroori hain.
6. **Cost split**: dono LLMs ke `usage` tokens alag print karo (travel agent vs orchestrator) aur dekho kaun zyada kharch karta hai.
