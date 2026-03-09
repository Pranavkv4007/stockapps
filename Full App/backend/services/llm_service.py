"""
Central LLM abstraction layer.
Replaces Streamlit-cached clients with lazy singletons.
"""

import os
import re
import json

from backend.config import OPENAI_MODEL, GPT4O, GEMINI_MODEL, CLAUDE_HAIKU, CLAUDE_SONNET, CLAUDE_OPUS

# Lazy singletons
_openai_client = None
_gemini_client = None
_claude_client = None


def get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


def get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            return None
        from google import genai
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def get_claude_client():
    global _claude_client
    if _claude_client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return None
        import anthropic
        _claude_client = anthropic.Anthropic(api_key=api_key)
    return _claude_client


def build_prompt(system_prompt, user_prompt, model_name):
    if model_name == "gemini":
        return f"{system_prompt}\n\n{user_prompt}"
    elif model_name in ("openai", "gpt4o"):
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    return None


def llm(system_prompt, user_prompt, model_name):
    match model_name:
        case "gemini":
            gemini_client = get_gemini_client()
            if gemini_client is None:
                raise ValueError("GOOGLE_API_KEY is not set.")
            prompts = build_prompt(system_prompt, user_prompt, "gemini")
            response = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[{"role": "user", "parts": [{"text": prompts}]}],
            )
            return response.candidates[0].content.parts[0].text
        case "openai":
            openai_client = get_openai_client()
            if openai_client is None:
                raise ValueError("OPENAI_API_KEY is not set.")
            prompts = build_prompt(system_prompt, user_prompt, "openai")
            response = openai_client.chat.completions.create(
                model=OPENAI_MODEL, messages=prompts
            )
            return response.choices[0].message.content
        case "gpt4o":
            openai_client = get_openai_client()
            if openai_client is None:
                raise ValueError("OPENAI_API_KEY is not set.")
            prompts = build_prompt(system_prompt, user_prompt, "openai")
            response = openai_client.chat.completions.create(
                model=GPT4O, messages=prompts
            )
            return response.choices[0].message.content
        case "claude-haiku" | "claude-sonnet" | "claude-opus":
            claude_client = get_claude_client()
            if claude_client is None:
                raise ValueError("ANTHROPIC_API_KEY is not set.")
            claude_model = {
                "claude-haiku": CLAUDE_HAIKU,
                "claude-sonnet": CLAUDE_SONNET,
                "claude-opus": CLAUDE_OPUS,
            }[model_name]
            response = claude_client.messages.create(
                model=claude_model,
                max_tokens=8096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text
        case _:
            return "Unknown model"


def llm_json(system_prompt, user_prompt):
    """Call OpenAI with JSON response format for structured output."""
    openai_client = get_openai_client()
    if openai_client is None:
        raise ValueError("OPENAI_API_KEY is not set.")
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content


def gemini_llm_kpi(system_prompt, user_prompt, company_name):
    """Gemini Search with grounding tool."""
    from google.genai import types

    gemini_client = get_gemini_client()
    if gemini_client is None:
        raise ValueError("GOOGLE_API_KEY is not set.")
    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(
        tools=[grounding_tool], system_instruction=system_prompt
    )
    contents = [
        types.Content(role="user", parts=[types.Part(text=user_prompt)])
    ]
    response = gemini_client.models.generate_content(
        model=GEMINI_MODEL, contents=contents, config=config
    )
    return response.text


def clean_and_parse_json(llm_output):
    cleaned = llm_output.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip().strip("'").strip('"')
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def clean_text_for_llm(text):
    text = re.sub(r"\[cite:.*?\]", "", text)
    text = re.sub(r"[🔴🟢🟡🔵⚪⚫🟠🟣🟤✅❌⭐]", "", text)
    text = re.sub(r"\n\s*:[-:|\s]+\n", "\n", text)
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        if "|" in line:
            cells = line.split("|")
            if any(len(cell.strip()) > 500 for cell in cells):
                continue
        cleaned_lines.append(line)
    text = "\n".join(cleaned_lines)
    text = re.sub(r"#{4,}", "###", text)
    text = re.sub(r" +", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)
    return text.strip()


def check_api_status():
    """Test connectivity to all 3 models."""
    test_sp = "You are an AI assistant"
    test_up = "Respond with your model name only"
    results = {}
    for model_label, model_key in [("OpenAI", "openai"), ("GPT-4o", "gpt4o"), ("Gemini", "gemini"), ("Claude Haiku", "claude-haiku"), ("Claude Sonnet", "claude-sonnet"), ("Claude Opus", "claude-opus")]:
        try:
            llm(test_sp, test_up, model_key)
            results[model_label] = {"ok": True, "error": None}
        except Exception as e:
            results[model_label] = {"ok": False, "error": str(e)}
    return results
