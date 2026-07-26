from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import ROOT, Settings
from app.models import Base, ProductImport


def make_engine(settings: Settings):
    url = settings.database_url
    if url.startswith("sqlite:///data/"):
        (ROOT / "data").mkdir(exist_ok=True)
        url = f"sqlite:///{(ROOT / url.removeprefix('sqlite:///')).as_posix()}"
    return create_engine(url)


def init_db(settings: Settings):
    engine = make_engine(settings)
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def recent(session: Session, user_id: int, limit: int = 10) -> list[ProductImport]:
    stmt = (select(ProductImport).where(ProductImport.telegram_user_id == user_id)
            .order_by(ProductImport.id.desc()).limit(limit))
    return list(session.scalars(stmt))
