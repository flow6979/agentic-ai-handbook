"""Memory demo: personal assistant jo sessions ke beech yaad rakhta hai.

    python 02-agentic-architectures/12-memory/main.py --user vaibhav
        commands:  /end  (session khatam: facts extract + episode save)
                   /facts (saved facts dekho)   /forget <id>   /quit
    python 02-agentic-architectures/12-memory/main.py --offline   # 2 sessions, scripted
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from agentkit import ScriptedLLM, Tracer, call, get_llm, tool_response

from memory_assistant import PersonalAssistant

STORE = Path(__file__).parent / ".memory_store"


def offline_demo() -> None:
    j = json.dumps
    llm = ScriptedLLM([
        # --- session 1 ---
        tool_response(call("remember", fact="User is vegetarian", category="preference")),
        "Noted, you're vegetarian! Pune has great veg food.",
        "Sure, I'll keep replies short.",
        # end_session: extraction + episode summary
        j({"facts": [{"text": "User lives in Pune", "category": "personal"},
                     {"text": "User prefers short replies", "category": "preference"},
                     {"text": "User is vegetarian and does not eat eggs", "category": "preference"}]}),
        "User introduced themselves (vegetarian, lives in Pune, likes short replies).",
        # --- session 2 (naya assistant object = naya process jaisa) ---
        "Try paneer tikka at a veg place in Koregaon Park, Pune. No eggs, promise.",
    ])
    with tempfile.TemporaryDirectory() as store:
        print("===== SESSION 1 =====")
        a1 = PersonalAssistant(llm, "demo", store, tracer=Tracer(name="s1", verbose=False))
        for msg in ["Hi! I'm vegetarian and I live in Pune.", "Also, please keep your replies short."]:
            print(f"you: {msg}\nbot: {a1.chat(msg)}")
        stored = a1.end_session()
        print(f"\n[end_session] extracted facts: {stored['facts']}\n[end_session] episode: {stored['episode']}")
        print(f"[db] all facts now: {[f.text for f in a1.semantic.all('demo')]}")
        print("     ^ notice: 'User is vegetarian' aur '... does not eat eggs' dono save hue. Hashing embedder ke liye\n"
              "       yeh 'duplicate' nahi hain. Real embeddings / LLM-based reconcile isse merge karta (CONCEPTS.md dekho).")

        print("\n===== SESSION 2 (fresh assistant, only long-term memory) =====")
        a2 = PersonalAssistant(llm, "demo", store, tracer=Tracer(name="s2", verbose=False))
        msg = "Suggest something for dinner tonight"
        print(f"you: {msg}\nbot: {a2.chat(msg)}")
        print(f"\n[system prompt injected for this turn]\n{a2.last_system_prompt}")


def repl(user: str) -> None:
    a = PersonalAssistant(get_llm(), user, STORE, tracer=Tracer(name="assistant"))
    print(f"Chatting as {user!r}. Memory store: {STORE}. Commands: /end /facts /forget <id> /quit")
    while True:
        try:
            text = input("you: ").strip()
        except EOFError:
            text = "/quit"
        if text in ("/quit", "/exit"):
            print(a.end_session())
            return
        if text == "/end":
            print(a.end_session())
        elif text == "/facts":
            for f in a.semantic.all(user):
                print(f"  #{f.id} [{f.category}] {f.text}")
        elif text.startswith("/forget "):
            a.semantic.delete(int(text.split()[1]))
            print("forgotten")
        elif text:
            print(f"bot: {a.chat(text)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default="me")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    offline_demo() if args.offline else repl(args.user)


if __name__ == "__main__":
    main()
