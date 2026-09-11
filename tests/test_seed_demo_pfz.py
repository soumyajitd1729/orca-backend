from pathlib import Path

import pytest

from app.scripts.seed_demo_pfz import (
    DEMO_SOURCE_NAME,
    DEMO_SOURCE_TYPE,
    _build_valid_time,
    _validate_row,
    seed_demo_pfz_from_excel,
)
from app.models.pfz_zone import PFZZone
from sqlalchemy import delete, func, select


def test_build_valid_time():
    dt = _build_valid_time("2026-05-16", "14:00:00")
    assert dt.year == 2026
    assert dt.month == 5
    assert dt.day == 16
    assert dt.hour == 14
    assert dt.minute == 0
    assert dt.second == 0


def test_validate_row_valid():
    row = {
        "Date": "2026-05-16",
        "Time_UTC": "14:00:00",
        "Latitude": 13.24,
        "Longitude": 79.08,
    }
    assert _validate_row(row, 1) is None


def test_validate_row_missing_date():
    row = {
        "Time_UTC": "14:00:00",
        "Latitude": 13.24,
        "Longitude": 79.08,
    }
    err = _validate_row(row, 1)
    assert err is not None
    assert "Date" in err


def test_validate_row_invalid_latitude():
    row = {
        "Date": "2026-05-16",
        "Time_UTC": "14:00:00",
        "Latitude": 999.0,
        "Longitude": 79.08,
    }
    err = _validate_row(row, 1)
    assert err is not None
    assert "latitude" in err.lower()


def test_validate_row_invalid_longitude():
    row = {
        "Date": "2026-05-16",
        "Time_UTC": "14:00:00",
        "Latitude": 13.24,
        "Longitude": -999.0,
    }
    err = _validate_row(row, 1)
    assert err is not None
    assert "longitude" in err.lower()


@pytest.mark.asyncio
async def test_seed_demo_pfz_marks_records_as_demo():
    from app.db.session import get_db

    async for db in get_db():
        await db.execute(delete(PFZZone).where(PFZZone.source_type == DEMO_SOURCE_TYPE))
        await db.commit()
        break

    async for db in get_db():
        try:
            result = await seed_demo_pfz_from_excel(
                db, Path("pfz_data/PFZ_Hackathon_Synthetic_Dataset_5000.xlsx")
            )
            assert result["imported"] > 0
            assert result["errors"] == 0

            stmt = select(PFZZone).where(PFZZone.source_type == DEMO_SOURCE_TYPE).limit(1)
            result = await db.execute(stmt)
            zone = result.scalar_one_or_none()
            assert zone is not None
            assert zone.source_type == DEMO_SOURCE_TYPE
            assert zone.source_name == DEMO_SOURCE_NAME
            assert zone.components.get("source_type") == DEMO_SOURCE_TYPE
            assert "pfz_probability" in zone.components
            assert "pfz_class" in zone.components
            assert "observation_id" in zone.components
        finally:
            await db.execute(delete(PFZZone).where(PFZZone.source_type == DEMO_SOURCE_TYPE))
            await db.commit()
            break


@pytest.mark.asyncio
async def test_seed_demo_pfz_idempotent():
    from app.db.session import get_db

    async for db in get_db():
        await db.execute(delete(PFZZone).where(PFZZone.source_type == DEMO_SOURCE_TYPE))
        await db.commit()
        break

    async for db in get_db():
        try:
            result1 = await seed_demo_pfz_from_excel(
                db, Path("pfz_data/PFZ_Hackathon_Synthetic_Dataset_5000.xlsx")
            )
            assert result1["imported"] > 0

            result2 = await seed_demo_pfz_from_excel(
                db, Path("pfz_data/PFZ_Hackathon_Synthetic_Dataset_5000.xlsx")
            )
            assert result2["imported"] == 0
            assert result2["skipped"] == result1["imported"]
        finally:
            await db.execute(delete(PFZZone).where(PFZZone.source_type == DEMO_SOURCE_TYPE))
            await db.commit()
            break


@pytest.mark.asyncio
async def test_seed_demo_pfz_new_record_includes_coordinates():
    from app.db.session import get_db

    async for db in get_db():
        await db.execute(delete(PFZZone).where(PFZZone.source_type == DEMO_SOURCE_TYPE))
        await db.commit()
        break

    async for db in get_db():
        try:
            result = await seed_demo_pfz_from_excel(
                db, Path("pfz_data/PFZ_Hackathon_Synthetic_Dataset_5000.xlsx")
            )
            assert result["imported"] > 0

            stmt = select(PFZZone).where(PFZZone.source_type == DEMO_SOURCE_TYPE).limit(1)
            result = await db.execute(stmt)
            zone = result.scalar_one_or_none()
            assert zone is not None
            comp = zone.components or {}
            assert "latitude" in comp
            assert "longitude" in comp
            assert isinstance(comp["latitude"], (int, float))
            assert isinstance(comp["longitude"], (int, float))
        finally:
            await db.execute(delete(PFZZone).where(PFZZone.source_type == DEMO_SOURCE_TYPE))
            await db.commit()
            break


@pytest.mark.asyncio
async def test_seed_demo_pfz_updates_missing_coordinates():
    from app.db.session import get_db

    async for db in get_db():
        await db.execute(delete(PFZZone).where(PFZZone.source_type == DEMO_SOURCE_TYPE))
        await db.commit()
        break

    async for db in get_db():
        try:
            await seed_demo_pfz_from_excel(
                db, Path("pfz_data/PFZ_Hackathon_Synthetic_Dataset_5000.xlsx")
            )
            stmt = select(PFZZone).where(PFZZone.source_type == DEMO_SOURCE_TYPE).limit(1)
            result = await db.execute(stmt)
            zone = result.scalar_one_or_none()
            assert zone is not None

            components = dict(zone.components or {})
            components.pop("latitude", None)
            components.pop("longitude", None)
            zone.components = components
            await db.commit()

            result2 = await seed_demo_pfz_from_excel(
                db, Path("pfz_data/PFZ_Hackathon_Synthetic_Dataset_5000.xlsx")
            )
            assert result2["skipped"] > 0
            assert result2["imported"] == 0

            stmt = select(PFZZone).where(PFZZone.id == zone.id)
            result = await db.execute(stmt)
            updated_zone = result.scalar_one_or_none()
            assert updated_zone is not None
            comp = updated_zone.components or {}
            assert "latitude" in comp
            assert "longitude" in comp
        finally:
            await db.execute(delete(PFZZone).where(PFZZone.source_type == DEMO_SOURCE_TYPE))
            await db.commit()
            break


@pytest.mark.asyncio
async def test_seed_demo_pfz_does_not_duplicate_existing():
    from app.db.session import get_db

    async for db in get_db():
        await db.execute(delete(PFZZone).where(PFZZone.source_type == DEMO_SOURCE_TYPE))
        await db.commit()
        break

    async for db in get_db():
        try:
            result1 = await seed_demo_pfz_from_excel(
                db, Path("pfz_data/PFZ_Hackathon_Synthetic_Dataset_5000.xlsx")
            )
            assert result1["imported"] > 0

            count_before = (await db.execute(
                select(func.count(PFZZone.id)).where(PFZZone.source_type == DEMO_SOURCE_TYPE)
            )).scalar()

            result2 = await seed_demo_pfz_from_excel(
                db, Path("pfz_data/PFZ_Hackathon_Synthetic_Dataset_5000.xlsx")
            )
            assert result2["imported"] == 0
            assert result2["skipped"] == result1["imported"]

            count_after = (await db.execute(
                select(func.count(PFZZone.id)).where(PFZZone.source_type == DEMO_SOURCE_TYPE)
            )).scalar()

            assert count_after == count_before
        finally:
            await db.execute(delete(PFZZone).where(PFZZone.source_type == DEMO_SOURCE_TYPE))
            await db.commit()
            break


@pytest.mark.asyncio
async def test_seed_demo_pfz_no_fabricated_official_score():
    from app.db.session import get_db

    async for db in get_db():
        await db.execute(delete(PFZZone).where(PFZZone.source_type == DEMO_SOURCE_TYPE))
        await db.commit()
        break

    async for db in get_db():
        try:
            await seed_demo_pfz_from_excel(
                db, Path("pfz_data/PFZ_Hackathon_Synthetic_Dataset_5000.xlsx")
            )
            stmt = select(PFZZone).where(PFZZone.source_type == DEMO_SOURCE_TYPE).limit(1)
            result = await db.execute(stmt)
            zone = result.scalar_one_or_none()
            assert zone is not None
            assert zone.score is not None
            assert zone.source_type == DEMO_SOURCE_TYPE
            assert "pfz_probability" in (zone.components or {})
            pfz_prob = zone.components.get("pfz_probability")
            assert pfz_prob is not None
            assert 0.0 <= pfz_prob <= 1.0
        finally:
            await db.execute(delete(PFZZone).where(PFZZone.source_type == DEMO_SOURCE_TYPE))
            await db.commit()
            break
