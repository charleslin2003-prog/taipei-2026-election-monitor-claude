"""Optional second-pass classifier using the Claude API.

Runs only when the ANTHROPIC_API_KEY secret is set. It reclassifies headlines
the rule engine has already handled, a batch at a time, and marks results with
"by": "llm". Without the key the site works on rule-based labels alone.
"""
from __future__ import annotations

import json
import os
import re

import requests

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")
API_VERSION = os.environ.get("ANTHROPIC_VERSION", "2023-06-01")

PROMPT = """你是台灣選舉新聞的標註員。以下是 2026 台北市長選舉相關的新聞標題（候選人：國民黨蔣萬安、民進黨沈伯洋）。
請逐則判斷，只輸出 JSON 陣列，每個元素格式：
{"id": "<原 id>", "kind": "攻擊|澄清回應|一般報導", "target": "蔣萬安|沈伯洋|不明|null", "attacker": "藍營|綠營|白營|境外官方|名嘴與節目|網友與粉專|不明|null"}
規則：
- 「攻擊」＝標題呈現某方批評、指控、嘲諷另一方或其陣營；target 是被批評的候選人（或其市府、競辦）。
- 「澄清回應」＝候選人或其陣營反駁、澄清針對自己的說法；target 填該候選人。
- 「一般報導」＝行程、政見、民調數字等中性報導；target 與 attacker 填 null。
- 只依標題文字判斷，不要加入你對事件真假的看法。

標題：
"""


def enabled() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def classify_batch(items: list[dict]) -> dict[str, dict]:
    lines = "\n".join(f'{it["id"]}\t{it["title"]}' for it in items)
    r = requests.post(
        API_URL,
        headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        },
        json={"model": MODEL, "max_tokens": 4000, "messages": [{"role": "user", "content": PROMPT + lines}]},
        timeout=90,
    )
    r.raise_for_status()
    text = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        raise ValueError("model reply had no JSON array")
    out = {}
    valid_kind = {"攻擊", "澄清回應", "一般報導"}
    for row in json.loads(m.group(0)):
        if not isinstance(row, dict) or row.get("kind") not in valid_kind:
            continue
        out[str(row.get("id"))] = {
            "kind": row["kind"],
            "target": row.get("target") if row.get("target") not in ("null", "") else None,
            "attacker": row.get("attacker") if row.get("attacker") not in ("null", "") else None,
        }
    return out
