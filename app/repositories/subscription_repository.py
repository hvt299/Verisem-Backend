from app.database.config import Collections
from app.repositories.base_repository import BaseRepository

class SubscriptionRepository(BaseRepository):
    collection_name = Collections.SUBSCRIPTIONS
