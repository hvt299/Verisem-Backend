from app.database.config import Collections
from app.repositories.base_repository import BaseRepository

class CreditGrantRepository(BaseRepository):
    collection_name = Collections.CREDIT_GRANTS
