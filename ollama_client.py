from datetime import datetime

import requests

from config import (
    OLLAMA_URL,
    OLLAMA_TAGS_URL,
    DEFAULT_MODEL,
    SIMPLE_NUM_PREDICT,
    SIMPLE_HISTORY_LIMIT,
    COMPLEX_NUM_PREDICT,
    COMPLEX_HISTORY_LIMIT,
    TEMPERATURE,
    TOP_P,
    REQUEST_TIMEOUT,
)


# More natural and consistent than the generic prompt in config.py.
SHORT_SYSTEM_PROMPT = """You are NICO, Richard Otieno's personal AI assistant.
Be warm, natural, and concise. Talk like a helpful conversation partner:
use plain language, contractions, and direct answers. Avoid robotic
introductions, repetitive summaries, and unnecessary lists. Richard is
your creator. If asked who created you, say Richard Otieno.
Be honest about what you know and what you can do."""

FULL_SYSTEM_PROMPT = """You are NICO, Richard Otieno's personal AI assistant.
Be friendly, thoughtful, and natural—not stiff or overly formal. Answer the
actual question first. Use clear everyday language and contractions. Keep
simple answers short; give detail when it helps. Ask a brief follow-up only
when it is genuinely needed. Don't pretend to be human or claim actions you
didn't perform. Richard Otieno created you."""

GREETING_INPUTS = {
    "hi", "hello", "hey", "hiya", "sup",
    "good morning", "good afternoon", "good evening",
    "how are you", "how's it going", "whats up", "what's up",
}

WEB_TRIGGERS = (
    "search the web",
    "search online",
    "look online",
    "look it up",
    "find online",
    "check online",
    "on the internet",
    "latest",
    "currently",
    "current price",
    "current weather",
    "today's news",
    "today news",
    "recent news",
    "breaking news",
    "this week",
    "this month",
    "up to date",
    "up-to-date",
    "right now",
    "as of today",
)


def check_connection():
    try:
        response = requests.get(OLLAMA_TAGS_URL, timeout=(3, 5))
        response.raise_for_status()
        return True
    except requests.RequestException:
        return False


def fetch_models():
    try:
        response = requests.get(OLLAMA_TAGS_URL, timeout=(3, 8))
        response.raise_for_status()
        data = response.json()

        models = [
            item["name"].strip()
            for item in data.get("models", [])
            if isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and item["name"].strip()
        ]
        return list(dict.fromkeys(models)) or [DEFAULT_MODEL]

    except (requests.RequestException, ValueError):
        return [DEFAULT_MODEL]


def warm_model(model=None):
    """Load the selected model in the background to reduce first-reply delay."""
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": model or DEFAULT_MODEL,
                "messages": [
                    {"role": "user", "content": "Reply with OK."}
                ],
                "stream": False,
                "keep_alive": "10m",
                "options": {
                    "num_predict": 1,
                    "temperature": 0,
                },
            },
            timeout=(3, 60),
        )
        response.raise_for_status()
        return True
    except requests.RequestException:
        return False


def should_search_web(user_message):
    """Search only when the user asks for live or explicitly online info."""
    text = user_message.lower().strip()
    if not text:
        return False

    if text in GREETING_INPUTS:
        return False

    # Conversational and creative requests should get a quick local response.
    quick_phrases = (
        "how are you",
        "how's it going",
        "thank you",
        "thanks",
        "who made you",
        "who created you",
        "what can you do",
        "tell me a joke",
        "write a poem",
        "write a story",
        "write code",
        "help me brainstorm",
        "design a prototype",
        "make a prototype",
        "debug this",
        "fix this code",
    )
    if any(phrase in text for phrase in quick_phrases):
        return False

    return any(trigger in text for trigger in WEB_TRIGGERS)


def search_web(query, max_results=3):
    """Return a few web results, or [] if search is unavailable."""
    try:
        from ddgs import DDGS

        results = DDGS(timeout=5).text(
            query,
            max_results=max_results,
        )

        cleaned = []
        for result in results or []:
            if not isinstance(result, dict):
                continue

            url = result.get("href") or result.get("url")
            if not url:
                continue

            cleaned.append({
                "title": str(result.get("title") or "Web result"),
                "url": str(url),
                "snippet": str(
                    result.get("body") or result.get("snippet") or ""
                )[:1000],
            })

        return cleaned[:max_results]

    except Exception:
        return []


def _build_messages(
    history,
    user_message,
    knowledge_results=None,
    web_results=None,
    web_search_attempted=False,
):
    text = user_message.lower().strip()
    is_simple = (
        text in GREETING_INPUTS
        or len(user_message.split()) <= 5
    )

    if is_simple:
        system_prompt = SHORT_SYSTEM_PROMPT
        history_limit = SIMPLE_HISTORY_LIMIT
        num_predict = min(SIMPLE_NUM_PREDICT, 80)
    else:
        system_prompt = FULL_SYSTEM_PROMPT
        history_limit = COMPLEX_HISTORY_LIMIT
        num_predict = min(COMPLEX_NUM_PREDICT, 220)

    local_date = datetime.now().astimezone().strftime("%Y-%m-%d")
    system_prompt += f"\nLocal date: {local_date}."

    if web_results:
        system_prompt += (
            "\nUse the supplied search results for current facts. "
            "Do not invent details or citations. If results are incomplete "
            "or disagree, be clear about that."
        )

        for index, result in enumerate(web_results[:3], start=1):
            system_prompt += (
                f"\n\nSearch result {index}:"
                f"\nTitle: {result['title']}"
                f"\nURL: {result['url']}"
                f"\nSnippet: {result['snippet']}"
            )
    elif web_search_attempted:
        system_prompt += (
            "\nA live search was attempted but returned no results. "
            "Be upfront that you could not verify current information."
        )

    if knowledge_results:
        system_prompt += "\n\nUseful information from local knowledge:"
        for item in knowledge_results[:3]:
            system_prompt += (
                f"\n- {item.get('title', 'Untitled')}: "
                f"{str(item.get('snippet', ''))[:250]}"
            )

    valid_history = [
        {
            "role": item["role"],
            "content": item["content"],
        }
        for item in history
        if isinstance(item, dict)
        and item.get("role") in ("user", "assistant")
        and isinstance(item.get("content"), str)
    ]

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(valid_history[-history_limit:])
    messages.append({"role": "user", "content": user_message})

    return messages, num_predict


def ask(
    model,
    history,
    user_message,
    knowledge_results=None,
    web_results=None,
    web_search_attempted=False,
):
    if not isinstance(user_message, str) or not user_message.strip():
        return "What would you like to ask?", True

    messages, num_predict = _build_messages(
        history=history,
        user_message=user_message,
        knowledge_results=knowledge_results,
        web_results=web_results,
        web_search_attempted=web_search_attempted,
    )

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": model or DEFAULT_MODEL,
                "messages": messages,
                "stream": False,
                "keep_alive": "10m",
                "options": {
                    "num_predict": num_predict,
                    "temperature": TEMPERATURE,
                    "top_p": TOP_P,
                },
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()

        data = response.json()
        message = data.get("message", {})
        answer = (
            message.get("content", "").strip()
            if isinstance(message, dict)
            else ""
        )

        return answer or "I didn't get a response that time—try again?", True

    except requests.exceptions.ConnectionError:
        return (
            "I can't reach Ollama right now. Make sure it's running, "
            "then try again.",
            False,
        )
    except requests.exceptions.Timeout:
        return "That took too long. Could you try once more?", True
    except requests.exceptions.HTTPError as error:
        status = getattr(error.response, "status_code", "unknown")
        return (
            f"Ollama returned HTTP {status}. Check that the selected "
            "model is installed.",
            False,
        )
    except (requests.RequestException, ValueError) as error:
        return f"I hit a problem with the Ollama request: {error}", False
    except Exception as error:
        return f"Something unexpected went wrong: {error}", False