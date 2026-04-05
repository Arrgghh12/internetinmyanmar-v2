"""
Central model routing — agents/utils/model_router.py
Every agent imports this. Never hardcode model names elsewhere.

5-level stack:
  L1  Tavily       — web search ($0.005/search)
  L2  Groq Llama   — free classification, language detection
  L3  Qwen 2.5 72B — neutral Burmese translation only
  L4  DeepSeek-V3  — public data consolidation
  L5  Claude       — all editorial + any sensitive content

Safety rule: is_sensitive() = True → Claude only, always.
"""

import json
import os

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

# ── Lazy client init ──────────────────────────────────────────────────────────

_claude      = None
_groq        = None
_together    = None
_openrouter  = None
_tavily      = None


def _get_claude():
    global _claude
    if _claude is None:
        _claude = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _claude


def _get_groq():
    global _groq
    if _groq is None:
        from groq import Groq
        _groq = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return _groq


def _get_together():
    global _together
    if _together is None:
        # Support both Together AI and Alibaba DashScope (both serve Qwen)
        if os.getenv("DASHSCOPE_API_KEY"):
            from openai import OpenAI
            _together = OpenAI(
                api_key=os.getenv("DASHSCOPE_API_KEY"),
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
        else:
            from together import Together
            _together = Together(api_key=os.getenv("TOGETHER_API_KEY"))
    return _together


def _get_openrouter():
    global _openrouter
    if _openrouter is None:
        from openai import OpenAI
        # Prefer direct DeepSeek API, fall back to OpenRouter
        if os.getenv("DEEPSEEK_API_KEY"):
            _openrouter = OpenAI(
                base_url="https://api.deepseek.com/v1",
                api_key=os.getenv("DEEPSEEK_API_KEY"),
            )
        else:
            _openrouter = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=os.getenv("OPENROUTER_API_KEY"),
            )
    return _openrouter


def _get_tavily():
    global _tavily
    if _tavily is None:
        from tavily import TavilyClient
        _tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    return _tavily


# ── Safety check ──────────────────────────────────────────────────────────────

CHINA_SIGNALS = [
    "china", "chinese", "beijing", "shanghai", "alibaba",
    "geedge", "tiangou", "huawei", "zte", "hikvision",
    "great firewall", "fang binxing", "surveillance technology",
    "censorship export", "prc", "ccp", "state security",
    "mss", "ministry of public security",
]

SOURCE_SIGNALS = [
    "journalist", "arrested", "detention", "exile",
    "source", "informant", "identity", "real name",
    "location", "address", "in hiding", "undercover",
    "anonymous", "protected", "at risk", "threatened",
]


def is_sensitive(content: str, metadata: dict | None = None) -> bool:
    """
    True → Claude only.
    Covers: China-related content, at-risk individuals, private sources.
    When in doubt, return True.
    """
    if metadata is None:
        metadata = {}
    c = content.lower()
    if any(k in c for k in CHINA_SIGNALS):
        return True
    if any(k in c for k in SOURCE_SIGNALS):
        return True
    if metadata.get("source_tier") == 3:
        return True
    if metadata.get("has_names"):
        return True
    if metadata.get("telegram_origin"):
        return True
    return False


# ── Task routing ──────────────────────────────────────────────────────────────

# Tasks always on Claude regardless of sensitivity
ALWAYS_CLAUDE = {
    "brief_generate", "article_write", "amend_brief",
    "translate_fr", "translate_es", "translate_it",
}

# Routeable tasks: (provider, default_max_tokens)
ROUTEABLE = {
    "classify":       ("groq",      150),
    "detect_lang":    ("groq",       50),
    "extract_meta":   ("groq",      200),
    "consolidate":    ("deepseek", 1500),
    "anomaly_detect": ("deepseek",  500),
    "translate_mm":   ("qwen",     1000),
    "summarize_mm":   ("qwen",      400),
    "seo_generate":   ("haiku",     200),
}


def call(
    task: str,
    prompt: str,
    content: str = "",
    metadata: dict | None = None,
    max_tokens: int | None = None,
) -> str:
    """
    Route a task to the correct model and return the text response.

    task:     key from ALWAYS_CLAUDE or ROUTEABLE
    prompt:   instruction to the model
    content:  the text being processed
    metadata: dict with optional flags (source_tier, has_names, telegram_origin)
    """
    if metadata is None:
        metadata = {}

    full_text = (prompt + " " + content).strip()

    if task in ALWAYS_CLAUDE:
        return _call_claude("sonnet", prompt, content, max_tokens or 3000)

    if is_sensitive(full_text, metadata):
        tier = "haiku" if task in ("seo_generate", "classify") else "sonnet"
        return _call_claude(tier, prompt, content, max_tokens or 1000)

    if task in ROUTEABLE:
        provider, default_tok = ROUTEABLE[task]
        tokens = max_tokens or default_tok

        if provider == "groq":
            return _call_groq(prompt, content, tokens)
        elif provider == "qwen":
            return _call_qwen(prompt, content, tokens)
        elif provider == "deepseek":
            return _call_deepseek(prompt, content, tokens)
        elif provider == "haiku":
            return _call_claude("haiku", prompt, content, tokens)

    # Fallback
    return _call_claude("sonnet", prompt, content, max_tokens or 1000)


# ── Web search (not an LLM) ────────────────────────────────────────────────────

TRUSTED_DOMAINS = [
    "ooni.org", "netblocks.org", "rsf.org", "freedomhouse.org",
    "irrawaddy.com", "dvb.no", "accessnow.org", "citizenlab.ca",
    "myanmar-now.org", "mizzima.com", "athan.asia",
]


def search(query: str, max_results: int = 5, trusted_only: bool = True) -> list[dict]:
    """
    Tavily search. Returns list of {url, title, content, score}.
    trusted_only=True restricts to known reliable sources.
    """
    client = _get_tavily()
    params = dict(
        query=query,
        search_depth="advanced",
        max_results=max_results,
    )
    if trusted_only:
        params["include_domains"] = TRUSTED_DOMAINS
    response = client.search(**params)
    return response.get("results", [])


# ── Provider implementations ──────────────────────────────────────────────────

def _call_claude(tier: str, prompt: str, content: str, max_tokens: int) -> str:
    model = {"haiku": "claude-haiku-4-5", "sonnet": "claude-sonnet-4-6"}[tier]
    client = _get_claude()
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=(
            "Respond with the exact requested output only. "
            "No preamble. No explanation. No markdown fences unless output is code."
        ),
        messages=[{"role": "user", "content": f"{prompt}\n\n{content}".strip()}],
    )
    return resp.content[0].text


def _call_groq(prompt: str, content: str, max_tokens: int) -> str:
    client = _get_groq()
    resp = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": f"{prompt}\n\n{content[:2000]}"}],
        max_tokens=max_tokens,
        temperature=0,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content


def _call_qwen(prompt: str, content: str, max_tokens: int) -> str:
    client = _get_together()
    # DashScope uses different model name format than Together AI
    model = "qwen-plus" if os.getenv("DASHSCOPE_API_KEY") else "Qwen/Qwen2.5-72B-Instruct-Turbo"
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Respond with the exact requested output only. No preamble."},
            {"role": "user", "content": f"{prompt}\n\n{content}"},
        ],
        max_tokens=max_tokens,
        temperature=0.1,
    )
    return resp.choices[0].message.content


def _call_deepseek(prompt: str, content: str, max_tokens: int) -> str:
    client = _get_openrouter()
    # Direct DeepSeek API uses "deepseek-chat", OpenRouter uses "deepseek/deepseek-chat"
    model = "deepseek-chat" if os.getenv("DEEPSEEK_API_KEY") else "deepseek/deepseek-chat"
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Respond with JSON only. No preamble."},
            {"role": "user", "content": f"{prompt}\n\n{content}"},
        ],
        max_tokens=max_tokens,
        temperature=0,
    )
    return resp.choices[0].message.content
