import os
from dataclasses import dataclass


@dataclass
class Settings:
    app_name: str = os.getenv("APP_NAME", "AI Content SaaS")
    environment: str = os.getenv("ENVIRONMENT", "development")
    cors_origin: str = os.getenv("CORS_ORIGIN", "*")
    frontend_url: str = os.getenv("FRONTEND_URL", "")

    database_url: str = os.getenv("DATABASE_URL", "")

    groq_api_base_url: str = os.getenv("GROQ_API_BASE_URL", "https://api.groq.com/openai/v1")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "llama3-8b-8192")

    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_jwks_url: str = os.getenv("SUPABASE_JWKS_URL", "")

    linkedin_client_id: str = os.getenv("LINKEDIN_CLIENT_ID", "")
    linkedin_client_secret: str = os.getenv("LINKEDIN_CLIENT_SECRET", "")
    linkedin_redirect_uri: str = os.getenv("LINKEDIN_REDIRECT_URI", "")

    state_signing_secret: str = os.getenv("STATE_SIGNING_SECRET", "")
    encryption_key: str = os.getenv("ENCRYPTION_KEY", "")

    timezone: str = os.getenv("APP_TIMEZONE", "Asia/Karachi")


settings = Settings()
