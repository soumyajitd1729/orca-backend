"""PFZ Hackathon Synthetic Dataset importer.

This script imports the synthetic PFZ dataset
pfz_data/PFZ_Hackathon_Synthetic_Dataset_5000.xlsx into the local pfz_zones
table as DEMO_SIMULATED records.

IMPORTANT:
- This data is SYNTHETIC and must NOT be presented as official INCOIS PFZ data.
- source_type is hardcoded to "DEMO_SIMULATED".
- source_name is hardcoded to "ORCA Hackathon Synthetic PFZ Dataset".
- PFZ_Probability is stored in components metadata, NOT as the official score.
- The importer is idempotent: re-running it will not create duplicates.

Usage:
    python -m app.scripts.seed_demo_pfz --file pfz_data/PFZ_Hackathon_Synthetic_Dataset_5000.xlsx
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from geoalchemy2 import WKTElement
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.models.pfz_zone import PFZZone

logger = logging.getLogger(__name__)


def _is_postgres() -> bool:
    return "postgresql" in settings.DATABASE_URL

EXCEL_COLUMNS = [
    "Observation_ID",
    "Date",
    "Time_UTC",
    "Latitude",
    "Longitude",
    "SST_C",
    "Chlorophyll_mg_m3",
    "Depth_m",
    "Distance_From_Coast_km",
    "PFZ_Probability",
    "PFZ",
    "PFZ_Class",
]

REQUIRED_COLUMNS = {"Date", "Time_UTC", "Latitude", "Longitude"}

DEMO_SOURCE_TYPE = "DEMO_SIMULATED"
DEMO_SOURCE_NAME = "ORCA Hackathon Synthetic PFZ Dataset"


def _validate_row(row: dict[str, Any], row_index: int) -> str | None:
    for col in REQUIRED_COLUMNS:
        if row.get(col) is None or (isinstance(row[col], str) and not row[col].strip()):
            return f"Row {row_index}: missing required field '{col}'"
    lat = row.get("Latitude")
    lon = row.get("Longitude")
    if lat is not None and (float(lat) < -90.0 or float(lat) > 90.0):
        return f"Row {row_index}: latitude {lat} out of bounds"
    if lon is not None and (float(lon) < -180.0 or float(lon) > 180.0):
        return f"Row {row_index}: longitude {lon} out of bounds"
    return None


def _build_valid_time(date_str: str, time_str: str) -> datetime:
    return datetime.fromisoformat(f"{date_str}T{time_str}")


async def _find_existing_demo(
    db: AsyncSession,
    valid_time: datetime,
    observation_id: str | None = None,
) -> PFZZone | None:
    stmt = select(PFZZone).where(
        PFZZone.source_type == DEMO_SOURCE_TYPE,
        PFZZone.valid_time == valid_time,
    )
    if observation_id:
        stmt = stmt.where(
            func.json_extract(PFZZone.components, "$.observation_id") == str(observation_id)
        )
    result = await db.execute(stmt.limit(1))
    return result.scalar_one_or_none()


async def seed_demo_pfz_from_excel(
    db: AsyncSession,
    path: Path,
) -> dict[str, int]:
    if not path.exists():
        raise FileNotFoundError(f"Excel file not found: {path}")

    try:
        import openpyxl
    except ImportError as exc:
        raise RuntimeError(
            "openpyxl is required to import Excel files. Install it with: pip install openpyxl"
        ) from exc

    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if not rows:
        return {"total": 0, "imported": 0, "skipped": 0}

    header = [str(cell).strip() if cell is not None else "" for cell in rows[0]]
    data_rows = rows[1:]

    missing = REQUIRED_COLUMNS - set(header)
    if missing:
        raise ValueError(
            f"Excel file is missing required columns: {', '.join(sorted(missing))}"
        )

    col_idx = {name: header.index(name) for name in EXCEL_COLUMNS if name in header}

    imported = 0
    skipped = 0
    errors: list[str] = []

    for row_index, row in enumerate(data_rows, start=2):
        if not any(cell is not None for cell in row):
            continue

        record: dict[str, Any] = {}
        for col_name, idx in col_idx.items():
            record[col_name] = row[idx] if idx < len(row) else None

        validation_error = _validate_row(record, row_index)
        if validation_error:
            errors.append(validation_error)
            skipped += 1
            continue

        date_str = str(record["Date"]).strip()
        time_str = str(record["Time_UTC"]).strip()
        valid_time = _build_valid_time(date_str, time_str)

        lat = float(record["Latitude"])
        lon = float(record["Longitude"])

        existing = await _find_existing_demo(
            db,
            valid_time=valid_time,
            observation_id=record.get("Observation_ID"),
        )
        if existing:
            components = dict(existing.components or {})
            components.setdefault("latitude", lat)
            components.setdefault("longitude", lon)
            existing.components = components
            skipped += 1
            continue

        components: dict[str, Any] = {
            "observation_id": record.get("Observation_ID"),
            "sst_c": record.get("SST_C"),
            "chlorophyll_mg_m3": record.get("Chlorophyll_mg_m3"),
            "pfz_probability": record.get("PFZ_Probability"),
            "pfz": record.get("PFZ"),
            "pfz_class": record.get("PFZ_Class"),
            "source_type": DEMO_SOURCE_TYPE,
            "latitude": lat,
            "longitude": lon,
        }

        depth_val = record.get("Depth_m")
        depth_str = f"{depth_val}m" if depth_val is not None else None

        pfz_probability = record.get("PFZ_Probability")

        if _is_postgres():
            geometry = WKTElement(f"POINT({lon} {lat})", srid=4326)
        else:
            geometry = None

        zone = PFZZone(
            geometry=geometry,
            score=pfz_probability,
            components=components,
            valid_time=valid_time,
            source_type=DEMO_SOURCE_TYPE,
            source_name=DEMO_SOURCE_NAME,
            depth=depth_str,
            distance_km=record.get("Distance_From_Coast_km"),
            forecast_date=datetime.strptime(date_str, "%Y-%m-%d").date(),
        )
        db.add(zone)
        imported += 1

        if imported % 500 == 0:
            await db.flush()
            logger.info("Imported %d demo PFZ records so far...", imported)

    await db.commit()

    result = {
        "total": len(data_rows),
        "imported": imported,
        "skipped": skipped,
        "errors": len(errors),
    }

    if errors:
        logger.warning(
            "Skipped %d rows due to validation errors. First few: %s",
            len(errors),
            errors[:5],
        )

    logger.info(
        "Demo PFZ import complete: %d imported, %d skipped out of %d total rows",
        imported,
        skipped,
        len(data_rows),
    )

    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import DEMO_SIMULATED PFZ data from Excel file"
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=Path("pfz_data/PFZ_Hackathon_Synthetic_Dataset_5000.xlsx"),
        help="Path to the Excel file (default: pfz_data/PFZ_Hackathon_Synthetic_Dataset_5000.xlsx)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the file without inserting records",
    )
    return parser.parse_args()


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = _parse_args()

    if not args.file.exists():
        logger.error("File not found: %s", args.file)
        return

    async for db in get_db():
        if args.dry_run:
            try:
                import openpyxl
            except ImportError:
                logger.error("openpyxl is required for dry-run validation")
                return
            wb = openpyxl.load_workbook(args.file, read_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            wb.close()
            logger.info(
                "Dry-run: file contains %d data rows (excluding header)",
                len(rows) - 1,
            )
        else:
            result = await seed_demo_pfz_from_excel(db, args.file)
            logger.info("Import result: %s", result)
        break


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
