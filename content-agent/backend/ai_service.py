import requests

from config.settings import settings

FALLBACK_MODELS = [settings.groq_model, "llama-3.1-8b-instant", "llama-3.3-70b-versatile"]


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


def generate_platform_posts(content: str) -> dict[str, str]:
    prompts = {
        "linkedin": "Write one professional LinkedIn post with strong hook and CTA.",
        "twitter": "Write one X/Twitter thread (4-6 tweets) with numbered format 1/,2/.",
        "facebook": "Write one Facebook post in conversational brand tone with CTA.",
        "instagram": "Write one Instagram caption with strong hook, CTA, and 6-10 relevant hashtags.",
        "blog_summary": "Write a concise blog-style summary with clear key takeaways in a professional tone.",
    }
    return {platform: _generate(content, prompt) for platform, prompt in prompts.items()}
