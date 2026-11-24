import json
import re
import time
from pathlib import Path
from typing import Any, Iterable

from config import MEMORY_FILE, KNOWLEDGE_DIR, EXPORTS_DIR, NOTES_DIR


def load_memory() -> list[dict[str, str]]:
    if not MEMORY_FILE.exists():
        return []

    try:
        with MEMORY_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(data, list):
        return []

    valid_roles = {"user", "assistant", "system"}
    return [
        item for item in data
        if isinstance(item, dict)
        and item.get("role") in valid_roles
        and isinstance(item.get("content"), str)
    ][-100:]  # Keep memory size bounded


def save_memory(messages: Iterable[dict[str, str]]) -> bool:
    """Atomically save conversation memory."""
    temporary_file = MEMORY_FILE.with_suffix(".json.tmp")

    try:
        MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with temporary_file.open("w", encoding="utf-8") as file:
            json.dump(
                list(messages)[-100:],
                file,
                indent=2,
                ensure_ascii=False,
            )
        temporary_file.replace(MEMORY_FILE)
        return True
    except (OSError, TypeError):
        if temporary_file.exists():
            try:
                temporary_file.unlink()
            except OSError:
                pass
        return False


def knowledge_path_for_url(url: str) -> Path:
    try:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", url).strip("_.")
        if not safe:
            safe = "unknown"
        return KNOWLEDGE_DIR / f"{safe[:180]}.json"
    except Exception:
        return KNOWLEDGE_DIR / "unknown.json"


def save_knowledge(
    url: str,
    title: str,
    content: str,
    entry_type: str = "page",
) -> bool:
    entry = {
        "url": url,
        "title": title,
        "fetched_at": time.strftime("%d %b %Y %H:%M:%S"),
        "type": entry_type,
        "content": content,
    }

    try:
        KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
        path = knowledge_path_for_url(url)
        temporary = path.with_suffix(".json.tmp")

        with temporary.open("w", encoding="utf-8") as file:
            json.dump(entry, file, indent=2, ensure_ascii=False)

        temporary.replace(path)
        return True
    except (OSError, TypeError):
        return False


def list_knowledge_files() -> list[Path]:
    try:
        KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
        return sorted(KNOWLEDGE_DIR.glob("*.json"))
    except OSError:
        return []


def search_knowledge(query: str, max_results: int = 3) -> list[dict[str, Any]]:
    if not isinstance(query, str) or not query.strip():
        return []

    terms = [
        term.lower()
        for term in query.split()
        if len(term) > 2
    ]
    if not terms:
        return []

    results: list[dict[str, Any]] = []

    for path in list_knowledge_files():
        try:
            with path.open("r", encoding="utf-8") as file:
                entry = json.load(file)
        except (OSError, json.JSONDecodeError):
            continue

        if not isinstance(entry, dict):
            continue

        content = str(entry.get("content", "")).lower()
        title = str(entry.get("title", "")).lower()

        score = sum(content.count(term) for term in terms)
        score += sum(title.count(term) * 2 for term in terms)

        if score > 0:
            plain_content = str(entry.get("content", ""))
            results.append({
                "title": entry.get("title", "Untitled"),
                "url": entry.get("url", ""),
                "score": score,
                "snippet": plain_content[:200],
            })

    results.sort(key=lambda item: item["score"], reverse=True)
    return results[:max_results]


def save_note(text: str) -> Path | None:
    if not isinstance(text, str):
        return None

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    path = NOTES_DIR / f"note_{timestamp}.txt"

    try:
        NOTES_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path
    except OSError:
        return None


def export_chat(chat_text: str, model_name: str) -> Path | None:
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    path = EXPORTS_DIR / f"nico_chat_{timestamp}.txt"

    lines = [
        "NICO Conversation Export",
        f"Date: {time.strftime('%d %b %Y %H:%M:%S')}",
        f"Model: {model_name}",
        "=" * 50,
        "",
    ]

    if chat_text:
        lines.append(chat_text)

    try:
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")
        return path
    except OSError:
        return None