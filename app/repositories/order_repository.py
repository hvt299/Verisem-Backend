from app.database.config import Collections
from app.repositories.base_repository import BaseRepository

class OrderRepository(BaseRepository):
    collection_name = Collections.ORDERS
