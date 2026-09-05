from app.database import Base, engine
from app.models.db_models import TranscriptChunk


Base.metadata.create_all(bind=engine)

print("Tables created successfully!")