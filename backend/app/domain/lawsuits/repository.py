from app.core.repository import BaseRepository
from app.domain.lawsuits.models import Lawsuit


class LawsuitRepository(BaseRepository[Lawsuit]):
    model = Lawsuit
