import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base
from app.models.base import TimestampMixin


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


PROVIDER_TYPES = ["openai_compatible", "mock"]


class Provider(Base, TimestampMixin):
    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(50), nullable=False, default="openai_compatible")
    base_url: Mapped[str] = mapped_column(String(500), default="")
    encrypted_api_key: Mapped[str | None] = mapped_column(Text)
    extra_headers_json: Mapped[str] = mapped_column(Text, default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    models: Mapped[list["ProviderModel"]] = relationship(
        back_populates="provider", cascade="all, delete-orphan"
    )

    @property
    def has_api_key(self) -> bool:
        return self.encrypted_api_key is not None and self.encrypted_api_key != ""


class ProviderModel(Base):
    __tablename__ = "provider_models"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    provider_id: Mapped[str] = mapped_column(String(36), ForeignKey("providers.id"), nullable=False)
    model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), default="")
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    provider: Mapped["Provider"] = relationship(back_populates="models")
