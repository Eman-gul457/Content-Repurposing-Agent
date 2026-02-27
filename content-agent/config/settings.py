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
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_image_model: str = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.0-flash-preview-image-generation")

    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_jwks_url: str = os.getenv("SUPABASE_JWKS_URL", "")
    supabase_service_role_key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    supabase_storage_bucket: str = os.getenv("SUPABASE_STORAGE_BUCKET", "post-media")

    linkedin_client_id: str = os.getenv("LINKEDIN_CLIENT_ID", "")
    linkedin_client_secret: str = os.getenv("LINKEDIN_CLIENT_SECRET", "")
    linkedin_redirect_uri: str = os.getenv("LINKEDIN_REDIRECT_URI", "")
    twitter_client_id: str = os.getenv("TWITTER_CLIENT_ID", "")
    twitter_client_secret: str = os.getenv("TWITTER_CLIENT_SECRET", "")
    twitter_redirect_uri: str = os.getenv("TWITTER_REDIRECT_URI", "")
    canva_client_id: str = os.getenv("CANVA_CLIENT_ID", "")
    canva_client_secret: str = os.getenv("CANVA_CLIENT_SECRET", "")
    canva_redirect_uri: str = os.getenv("CANVA_REDIRECT_URI", "")
    canva_scopes: str = os.getenv(
        "CANVA_SCOPES",
        "design:content:read design:content:write design:meta:read asset:read asset:write",
    )
    whatsapp_phone_number_id: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    whatsapp_business_account_id: str = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "")
    whatsapp_access_token: str = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    whatsapp_verify_token: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
    whatsapp_template_name: str = os.getenv("WHATSAPP_TEMPLATE_NAME", "hello_world")
    whatsapp_template_lang: str = os.getenv("WHATSAPP_TEMPLATE_LANG", "en_US")
    whatsapp_recipients: str = os.getenv("WHATSAPP_RECIPIENT_NUMBERS", "")

    state_signing_secret: str = os.getenv("STATE_SIGNING_SECRET", "")
    encryption_key: str = os.getenv("ENCRYPTION_KEY", "")

    timezone: str = os.getenv("APP_TIMEZONE", "Asia/Karachi")
    auto_generate_plan_images_on_run: bool = os.getenv("AUTO_GENERATE_PLAN_IMAGES_ON_RUN", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


settings = Settings()
