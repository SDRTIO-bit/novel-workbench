from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class _TestModel(Base):
    __tablename__ = "_test_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)


async def test_create_table_and_commit(db_session):
    item = _TestModel(name="test")
    db_session.add(item)
    await db_session.commit()

    result = await db_session.get(_TestModel, item.id)
    assert result is not None
    assert result.name == "test"


async def test_rollback(db_session):
    item = _TestModel(name="rollback_test")
    db_session.add(item)
    await db_session.flush()
    await db_session.rollback()

    result = await db_session.get(_TestModel, item.id)
    assert result is None
