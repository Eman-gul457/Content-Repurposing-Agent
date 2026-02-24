import requests

from config.settings import settings

FALLBACK_MODELS = [settings.groq_model, "llama-3.1-8b-instant", "llama-3.3-70b-versatile"]
SUPPORTED_PLATFORMS = ["linkedin", "twitter", "facebook", "instagram", "blog_summary"]
PLATFORM_PROMPTS = {
    "linkedin": "Write one professional LinkedIn post with strong hook, 3 key points, and CTA.",
    "twitter": "Write one X/Twitter thread (4-6 tweets) in numbered format 1/,2/.",
    "facebook": "Write one Facebook post in conversational brand tone with CTA.",
    "instagram": "Write one Instagram caption with strong hook, CTA, and 6-10 relevant hashtags.",
    "blog_summary": "Write a concise blog-style summary with key takeaways in professional tone.",
}


def _generate(content: str, instruction: str) -> str:
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is required")

    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }

    last_error = ""
    for model in FALLBACK_MODELS:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a senior social media content strategist."},
                {
                    "role": "user",
                    "content": f"{instruction}\n\nSource content:\n{content}",
                },
            ],
            "temperature": 0.7,
        }
        response = requests.post(
            f"{settings.groq_api_base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,
        )
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"].strip()
        last_error = f"model={model} status={response.status_code} body={response.text[:300]}"

    raise RuntimeError(f"Groq generation failed: {last_error}")


def _language_instruction(language_pref: str) -> str:
    pref = (language_pref or "english_urdu").strip().lower()
    if pref == "english":
        return "Return only English."
    if pref == "urdu":
        return "Return only Urdu in clear unicode script."
    return "Return bilingual output: English first then Urdu."


def generate_platform_posts(
    content: str,
    platforms: list[str] | None = None,
    language_pref: str = "english_urdu",
    profile_context: str = "",
) -> dict[str, str]:
    selected = platforms or SUPPORTED_PLATFORMS
    selected = [x for x in selected if x in SUPPORTED_PLATFORMS]
    if not selected:
        selected = ["linkedin", "twitter"]

    lang_line = _language_instruction(language_pref)
    context_line = f"Business context: {profile_context.strip()}" if profile_context.strip() else ""

    outputs: dict[str, str] = {}
    for platform in selected:
        base_prompt = PLATFORM_PROMPTS.get(platform, PLATFORM_PROMPTS["linkedin"])
        instruction = f"{base_prompt}\n{lang_line}\n{context_line}".strip()
        outputs[platform] = _generate(content, instruction)
    return outputs
