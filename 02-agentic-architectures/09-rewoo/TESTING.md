# 09-rewoo: Testing aur tinkering

## Setup
Repo root se `pip install -e ".[all]"`, `.env` mein `LLM_MODEL` + key.

## 1. Offline demo

```bash
python 02-agentic-architectures/09-rewoo/main.py --offline
```

Dekho:
- `parallel levels: [['#E1', '#E2', '#E3'], ['#E4'], ['#E5']]` → teen lookups parallel chale.
- `ReWOO -> llm_calls=2` vs `ReAct -> llm_calls=6`, aur input tokens ka farq (~3x).

## 2. Real LLM

```bash
python 02-agentic-architectures/09-rewoo/main.py --compare "How many times taller is Burj Khalifa than Qutub Minar?"
python 02-agentic-architectures/09-rewoo/main.py --compare "Population of India divided by population of Japan, in millions?"
```

Kya check karo:
- Kya model ne format sahi follow kiya (`#E1 = lookup[...]`)? Nahi kiya to `parse_plan` ka error message aayega.
- `--compare` mein dono ke `input_tokens` (real provider usage) compare karo.
- Kya dono ka answer same hai?

## 3. Offline tests

```bash
pytest 02-agentic-architectures/09-rewoo -v
```

Cover: plan parse + dependency levels, bad plan rejection (unknown tool, forward reference, empty),
end-to-end sirf 2 LLM calls, worker error evidence ban jata hai, `LLM[...]` worker + substitution.

## 4. Tinker karo

1. **Fail case:** pucho "Height of Taj Mahal divided by Qutub Minar?" (Taj data nahi hai). Evidence mein
   ERROR aayega. Solver kya bolta hai? Ab hybrid banao: koi evidence ERROR ho to `04-react` jaisa Agent chala do.
2. **Parallel vs sequential time:** `lookup` mein `time.sleep(1)` daalo. `ReWOO(..., parallel=False)` vs `True` ka time naapo.
3. **Few-shot planner:** `PLANNER_PROMPT` mein ek example plan daalo. Chhote model (`ollama:llama3.2`) pe
   parse errors kam hote hain?
4. **LLM worker:** `FACTS` mein value "8849 metres" kar do. Plan fail hoga (calculator). Planner ko sikhao
   ki `LLM[Extract only the number from #E1]` step use kare.
5. **Scale test:** 8 facts wala sawaal pucho. ReAct aur ReWOO ke tokens ka graph banao (steps vs tokens).
