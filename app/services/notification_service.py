"""Stage-aware notification orchestration, intentionally separate from alerts."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertEvent
from app.models.notification_binding import NotificationBinding
from app.repositories.notification_binding_repository import NotificationBindingRepository
from app.repositories.notification_delivery_repository import NotificationDeliveryRepository
from app.schemas.notification import NotificationDeliveryStatus, NotificationPlatform, NotificationProvider as ProviderName, NotificationStage
from app.services.alert_service import AlertTransition
from app.services.electricity_service import local_now
from app.services.notification_providers import NotificationProvider


class NotificationService:
    def __init__(self, session: AsyncSession, provider: NotificationProvider) -> None:
        self._session = session
        self._provider = provider
        self._bindings = NotificationBindingRepository(session)
        self._deliveries = NotificationDeliveryRepository(session)

    async def process_transitions(self, transitions: list[AlertTransition]) -> None:
        for transition in transitions:
            try:
                await self.process_event(transition.event, transition.stage)
            except Exception:
                # Notification is intentionally a best-effort side effect.
                # Never allow it to affect the already-committed alert episode.
                await self._session.rollback()

    async def process_event(self, event: AlertEvent, stage: NotificationStage) -> None:
        bindings = await self._bindings.list(event.user_id)
        for binding in bindings:
            if not (binding.enabled and binding.provider == ProviderName.ASTRBOT.value and binding.platform == NotificationPlatform.QQ.value):
                continue
            await self._deliver(binding, event, stage)

    async def _deliver(self, binding: NotificationBinding, event: AlertEvent, stage: NotificationStage) -> None:
        delivery = await self._deliveries.get(
            event_id=event.id, binding_id=binding.id, provider=binding.provider, stage=stage.value,
        )
        if delivery is not None and delivery.status in {NotificationDeliveryStatus.SUCCESS.value, NotificationDeliveryStatus.PENDING.value}:
            return
        now = local_now()
        try:
            if delivery is None:
                delivery = await self._deliveries.create_pending(
                    event_id=event.id, binding_id=binding.id, provider=binding.provider, stage=stage.value, now=now,
                )
            else:
                delivery.status, delivery.sent_at, delivery.error_message = NotificationDeliveryStatus.PENDING.value, None, None
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            return
        except SQLAlchemyError:
            await self._session.rollback()
            return

        try:
            result = await self._provider.send(binding, event, stage)
            if result.success:
                delivery.status, delivery.sent_at, delivery.error_message = NotificationDeliveryStatus.SUCCESS.value, local_now(), None
            else:
                delivery.status, delivery.error_message = NotificationDeliveryStatus.FAILED.value, self._safe_error(result.error_message)
        except Exception:
            delivery.status, delivery.error_message = NotificationDeliveryStatus.FAILED.value, "notification provider failed"
        try:
            await self._session.commit()
        except SQLAlchemyError:
            await self._session.rollback()

    @staticmethod
    def _safe_error(value: str | None) -> str:
        # Provider adapters must not propagate URLs, tokens, headers, or stack traces.
        return "notification provider failed"
