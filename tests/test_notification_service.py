import asyncio
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.database import Base
from app.models import alert, collection, electricity, notification_binding, notification_delivery, upstream_session, user  # noqa: F401
from app.models.notification_delivery import NotificationDelivery
from app.repositories.notification_binding_repository import NotificationBindingRepository
from app.schemas.common import ApiResponse
from app.schemas.electricity import AlertSettingsUpdate, ElectricityReading
from app.schemas.notification import NotificationDeliveryStatus, NotificationStage
from app.services.alert_service import AlertService
from app.services.monitoring_service import MonitoringService
from app.services.notification_providers import MockAstrBotNotifier, NotificationSendResult
from app.services.notification_service import NotificationService


def test_stage_aware_notification_delivery_is_user_scoped_and_idempotent(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'notifications.db').as_posix()}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with sessions() as session:
            bindings = NotificationBindingRepository(session)
            from app.services.electricity_service import local_now
            await bindings.upsert(1, "astrbot", "qq", "123456", True, local_now())
            await bindings.upsert(2, "astrbot", "qq", "654321", True, local_now())
            await session.commit()

            alerts = AlertService(session)
            settings = AlertSettingsUpdate(
                enabled=True, low_balance_enabled=True, balance_warning_threshold=10, balance_critical_threshold=5,
                low_remaining_days_enabled=False, remaining_days_warning_threshold=7, remaining_days_critical_threshold=3,
            )
            await alerts.save_settings(1, settings)
            await alerts.save_settings(2, settings)
            notifier = MockAstrBotNotifier()
            service = NotificationService(session, notifier)
            reading = ElectricityReading(area_id="2", building_id="b", floor_id="f", room_id="r", remaining_money=8, raw_data={})

            await service.process_transitions(await alerts.evaluate(1, reading))
            await service.process_transitions(await alerts.evaluate(1, reading))
            assert [call[0].user_id for call in notifier.calls] == [1]
            assert [call[2] for call in notifier.calls] == [NotificationStage.ACTIVATED]

            reading.remaining_money = 4
            await service.process_transitions(await alerts.evaluate(1, reading))
            reading.remaining_money = 30
            await service.process_transitions(await alerts.evaluate(1, reading))
            assert [call[2] for call in notifier.calls] == [
                NotificationStage.ACTIVATED, NotificationStage.ESCALATED, NotificationStage.RESOLVED,
            ]
            deliveries = list((await session.scalars(select(NotificationDelivery).order_by(NotificationDelivery.id))).all())
            assert [(item.stage, item.status) for item in deliveries] == [
                ("activated", "success"), ("escalated", "success"), ("resolved", "success"),
            ]

            await service.process_transitions(await alerts.evaluate(2, ElectricityReading(
                area_id="2", building_id="b", floor_id="f", room_id="r", remaining_money=8, raw_data={},
            )))
            assert notifier.calls[-1][0].user_id == 2
            assert notifier.calls[-1][0].target_id == "654321"
        await engine.dispose()

    asyncio.run(scenario())


def test_disabled_or_missing_binding_never_sends(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'disabled.db').as_posix()}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with sessions() as session:
            alerts = AlertService(session)
            settings = AlertSettingsUpdate(enabled=True, low_balance_enabled=True, balance_warning_threshold=10, balance_critical_threshold=5, low_remaining_days_enabled=False, remaining_days_warning_threshold=7, remaining_days_critical_threshold=3)
            await alerts.save_settings(1, settings)
            notifier = MockAstrBotNotifier()
            transition = await alerts.evaluate(1, ElectricityReading(area_id="2", building_id="b", floor_id="f", room_id="missing", remaining_money=8, raw_data={}))
            await NotificationService(session, notifier).process_transitions(transition)
            assert notifier.calls == []
            from app.services.electricity_service import local_now
            await NotificationBindingRepository(session).upsert(1, "astrbot", "qq", "123456", False, local_now())
            await session.commit()
            transition = await alerts.evaluate(1, ElectricityReading(area_id="2", building_id="b", floor_id="f", room_id="disabled", remaining_money=8, raw_data={}))
            await NotificationService(session, notifier).process_transitions(transition)
            assert notifier.calls == []
        await engine.dispose()
    asyncio.run(scenario())


def test_provider_failure_and_timeout_do_not_affect_alert_or_query(tmp_path: Path) -> None:
    class Client:
        async def query_electricity(self, **_: object) -> ApiResponse[ElectricityReading]:
            return ApiResponse.ok(ElectricityReading(area_id="2", building_id="b", floor_id="f", room_id="r", source_time="2026-09-01 04:00:00", remaining_money=8, raw_data={}))

    async def scenario() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'failure.db').as_posix()}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with sessions() as session:
            from app.services.electricity_service import local_now
            await NotificationBindingRepository(session).upsert(1, "astrbot", "qq", "123456", True, local_now())
            await session.commit()
            alerts = AlertService(session)
            await alerts.save_settings(1, AlertSettingsUpdate(enabled=True, low_balance_enabled=True, balance_warning_threshold=10, balance_critical_threshold=5, low_remaining_days_enabled=False, remaining_days_warning_threshold=7, remaining_days_critical_threshold=3))
            failed = MockAstrBotNotifier(result=NotificationSendResult(False, "safe failure"))
            result = await MonitoringService(notification_provider=failed).query_save_and_evaluate(1, session, Client(), area_id="2", building_id="b", floor_id="f", room_id="r")
            assert result.success
            delivery = (await session.scalars(select(NotificationDelivery))).one()
            assert delivery.status == NotificationDeliveryStatus.FAILED.value
            assert (await alerts.list_events(1, "2", "r", None, 10)).data

            timeout = MockAstrBotNotifier(exception=TimeoutError())
            reading = ElectricityReading(area_id="2", building_id="b", floor_id="f", room_id="timeout", remaining_money=8, raw_data={})
            await NotificationService(session, timeout).process_transitions(await alerts.evaluate(1, reading))
            timeout_delivery = (await session.scalars(select(NotificationDelivery).where(NotificationDelivery.stage == "activated").order_by(NotificationDelivery.id.desc()))).first()
            assert timeout_delivery and timeout_delivery.status == NotificationDeliveryStatus.FAILED.value
        await engine.dispose()
    asyncio.run(scenario())
