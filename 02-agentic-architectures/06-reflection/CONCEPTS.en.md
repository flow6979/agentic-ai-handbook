**Language:** [Hinglish](CONCEPTS.md) · English

# Reflection: an agent that checks and improves its own work

## 1. Idea

People write a first draft, read it, find mistakes, then improve it. An LLM's
first output is also often "okay-ish", not perfect. **Reflection** = giving the model feedback on its own output
and making it try again.

The most important question: **where does the feedback come from?**

```
 Feedback source            Pattern                    In this project
 ───────────────            ───────                    ───────────────
 Same/another LLM (opinion) Self-Refine / critic loop  reflection_refine.py
 Environment (facts)        Reflexion                  reflection_reflexion.py  (unit tests)
 Human                      Human feedback loop        see 11-human-in-the-loop
```

An LLM's opinion is subjective (it can approve something wrong too). Feedback from tests/compilers/validators
is objective. **Whenever you can get an objective signal, use it.**

## 2. Pattern 1: Self-Refine (Generate → Critique → Revise)

```
   Task
    │
    ▼
 ┌──────────┐   draft    ┌──────────────┐
 │GENERATOR │──────────► │   CRITIC     │  llm_json → Critique{score, issues, approved}
 └──────────┘            └──────┬───────┘
      ▲                         │
      │     issues              │ approved / score >= min?
      └─────────────────────────┤ no
                                │ yes
                                ▼
                            Final draft
```

- The critic's output is **structured** (the `Critique` pydantic model), so code can decide whether to
  stop the loop.
- Give the critic the task's **requirements**, otherwise it will give vague praise ("looks great!").
- The generator and critic can also be different models (the `critic_llm` param). A different model's "eyes"
  catch more blind spots.

## 3. Pattern 2: Reflexion (environment feedback + lessons memory)

Paper: Shinn et al., 2023. Three parts:

1. **Actor:** writes the code.
2. **Evaluator:** the environment. Here: unit tests, in a separate process, with a timeout.
3. **Self-reflection:** on failure the model itself writes "what went wrong, what to do next time".
   This verbal lesson goes into **memory** and into the next attempt's prompt.

```
            ┌───────────────────────────────────────────┐
            │ Lessons memory (lessons.json)             │
            │ - "normalise input before comparing"      │
            └──────────────┬────────────────────────────┘
                           │ injected into the prompt
                           ▼
   Task ──────────► ┌──────────────┐  code   ┌───────────────────┐
                    │   ACTOR      │────────►│ run_tests()       │
                    │ (write code) │         │ subprocess+timeout│
                    └──────────────┘         └────────┬──────────┘
                           ▲                    PASS? │
                           │                  ┌──yes──┴──no──┐
                           │                  ▼              ▼
                           │               Done      ┌──────────────┐
                           │                         │ REFLECT      │
                           └──── memory.add(lesson) ◄│ "what went   │
                                                     │  wrong?"     │
                                                     └──────────────┘
```

**Difference from self-refine:** a Reflexion lesson is **generalizable** and it persists.
Save it to a file and in the next run the agent has already "learned" it (this is a simple form of long-term
memory, see `12-memory`).

## 4. Variants / subtypes

| Variant | Feedback | Note |
|---|---|---|
| Self-Refine | same LLM as critic | simplest, subjective |
| Critic model (dual LLM) | a different LLM | fewer blind spots, more cost |
| Reflexion | environment + lessons memory | objective, learns |
| CRITIC (tool-verified) | the critic uses tools (search, calculator) to check facts | fixes hallucination |
| Constitutional / rubric review | a fixed list of principles | safety, style guides |
| Evaluator-optimizer workflow | fixed loop, separate evaluator | see `07-evaluator-optimizer` |
| LATS | reflection + tree search | combine with ToT (`10`) |

## 5. When to use it / when not

**Use it:** quality > latency (code generation, writing, SQL), and when there are clear criteria/tests.

**Don't use it:** simple lookups, low-latency chat, or when the critic has no criteria at all
(it will nitpick at random, or approve everything).

**Cost:** each round = 2 LLM calls (critique + revise). Always set `max_rounds`.

## 6. Production pitfalls

- **Sycophantic critic:** the same model approves its own output. Give it a strict rubric, or use a different model.
- **Over-editing:** things can also get worse in each round. Log each round's score and return the
  **best** draft, not just the last one (tinker exercise).
- **Sandbox:** LLM-written code is **untrusted**. `subprocess` is not a real sandbox: in production use Docker/gVisor/
  Firecracker/E2B, no network, CPU/memory limits.
- **Test leakage:** what if the model looks at the tests and hardcodes them (`if s == 'racecar': return True`)?
  Keep hidden tests that the model never sees.

## 7. How this project uses it

| Concept | File / function |
|---|---|
| Structured critique | `reflection_refine.py` → `Critique` |
| Generate → critique → revise loop, stop conditions | `reflection_refine.py` → `self_refine()` |
| Separate critic model support | `self_refine(..., critic_llm=...)` |
| Code runner (subprocess, `-I`, timeout, per-test report) | `reflection_sandbox.py` → `build_harness()`, `run_tests()` |
| Reflexion loop | `reflection_reflexion.py` → `solve_with_reflexion()` |
| Verbal lessons memory, JSON persist | `reflection_reflexion.py` → `LessonMemory` |
| Code extraction from markdown | `reflection_reflexion.py` → `extract_code()` |
