from supabase import create_client
from src.infrastructure_connections.config.settings import Settings


class SupabaseManager:
    _client = None

    @staticmethod
    def get_client():
        if SupabaseManager._client is None:

            url = Settings.get_supabase_url()
            key = Settings.get_supabase_key()

            if not url or not key:
                raise Exception("Missing Supabase config")

            SupabaseManager._client = create_client(url, key)

        return SupabaseManager._client
    
    
    
