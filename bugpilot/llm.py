
import json
import os
import logging
import re
import time
import threading

from openai import OpenAI, RateLimitError


logger = logging.getLogger(__name__)

MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "5"))

LLM_LOCK = threading.Lock()


def get_retry_delay(exc, attempt):

    response = getattr(exc, "response", None)

    if response is not None:
        retry_after = response.headers.get("retry-after")

        if retry_after:
            try:
                return max(1.0, float(retry_after)) + 2
            except ValueError:
                pass

    message = str(exc)

    match = re.search(
        r"try again in\s+([\d.]+)\s*s",
        message,
        re.IGNORECASE
    )

    if match:
        return float(match.group(1)) + 2

    return min(60, 5 * (2 ** attempt))


def ask_llm(system_prompt: str, user_prompt: str) -> dict:

    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not configured"
        )

    model = os.getenv(
        "GROQ_MODEL",
        "openai/gpt-oss-120b"
    )

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
        timeout=90.0,
        max_retries=0
    )

    started = time.perf_counter()

    with LLM_LOCK:

        for attempt in range(MAX_RETRIES + 1):

            try:

                logger.info(
                    "Groq model=%s attempt=%s/%s",
                    model,
                    attempt + 1,
                    MAX_RETRIES + 1
                )

                response = client.chat.completions.create(
                    model=model,
                    response_format={"type": "json_object"},
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                system_prompt
                                + "\nReturn only a valid JSON object."
                                + "\nDo not include Markdown."
                            )
                        },
                        {
                            "role": "user",
                            "content": user_prompt
                        }
                    ]
                )

                break

            except RateLimitError as exc:

                if attempt >= MAX_RETRIES:
                    raise RuntimeError(
                        "Groq rate limit exceeded after "
                        f"{MAX_RETRIES} retries"
                    ) from exc

                delay = get_retry_delay(exc, attempt)

                logger.warning(
                    "Groq rate limit reached. "
                    "Waiting %.2f seconds before retry.",
                    delay
                )

                time.sleep(delay)

    choice = response.choices[0]

    if choice.finish_reason == "length":
        raise RuntimeError(
            "Groq response was truncated"
        )

    content = choice.message.content

    if not content:
        raise RuntimeError(
            "Groq returned an empty response"
        )

    content = re.sub(
        r"^```(?:json)?\s*|\s*```$",
        "",
        content.strip(),
        flags=re.IGNORECASE
    ).strip()

    try:
        result = json.loads(content)

    except json.JSONDecodeError as exc:
        raise ValueError(
            "Groq returned invalid JSON"
        ) from exc

    if not isinstance(result, dict):
        raise ValueError(
            "Expected a JSON object from Groq"
        )

    latency_ms = round(
        (time.perf_counter() - started) * 1000,
        2
    )

    logger.info(
        "Groq response received in %s ms",
        latency_ms
    )

    if response.usage:
        logger.info(
            "Token usage: input=%s output=%s total=%s",
            response.usage.prompt_tokens,
            response.usage.completion_tokens,
            response.usage.total_tokens
        )

    return result






