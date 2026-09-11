import os
import sys
import uuid
import json
import re
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from geoalchemy2 import WKTElement

# Add current directory to python path
sys.path.insert(0, os.path.abspath("."))

from app.models.pfz_zone import PFZZone

def point_to_polygon_wkt(lon: float, lat: float, delta: float = 0.01) -> str:
    """Converts a (lon, lat) point into a closed bounding box POLYGON WKT string."""
    min_x, max_x = lon - delta, lon + delta
    min_y, max_y = lat - delta, lat + delta
    return f"POLYGON(({min_x:.5f} {min_y:.5f}, {max_x:.5f} {min_y:.5f}, {max_x:.5f} {max_y:.5f}, {min_x:.5f} {max_y:.5f}, {min_x:.5f} {min_y:.5f}))"

def parse_geometry_to_polygon(geom_val, lat=None, lon=None) -> str:
    """Ensures any input (POINT, POLYGON, or lat/lon) returns a valid POLYGON WKT string."""
    if pd.notna(geom_val):
        wkt_str = str(geom_val).strip()
        if wkt_str.upper().startswith("POLYGON"):
            return wkt_str
        elif wkt_str.upper().startswith("POINT"):
            match = re.search(r"POINT\s*\(\s*([-\d\.]+)\s+([-\d\.]+)\s*\)", wkt_str, re.IGNORECASE)
            if match:
                x, y = float(match.group(1)), float(match.group(2))
                return point_to_polygon_wkt(x, y)

    if pd.notna(lat) and pd.notna(lon):
        try:
            return point_to_polygon_wkt(float(lon), float(lat))
        except (ValueError, TypeError):
            pass

    # Default fallback box if no spatial info is present
    return "POLYGON((78.0 12.0, 79.0 12.0, 79.0 13.0, 78.0 13.0, 78.0 12.0))"

def seed_database(excel_path):
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is missing!")
        return

    # Standardize URL for sync SQLAlchemy engine
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    if database_url.startswith("postgresql+asyncpg://"):
        database_url = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    print(f"1. Reading Excel dataset from: {excel_path}")
    df = pd.read_excel(excel_path)
    print(f"   Found {len(df)} records in Excel file.")

    # Standardize column names
    df.columns = [col.strip().lower().replace(" ", "_") for col in df.columns]

    print("2. Connecting to Render PostgreSQL Database...")
    db_engine = create_engine(database_url)

    # Enable PostGIS extension on Render
    print("3. Enabling PostGIS extension on Render database...")
    with db_engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        conn.commit()

    # Create missing tables
    print("4. Ensuring database tables exist on Render...")
    PFZZone.metadata.create_all(bind=db_engine)

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = SessionLocal()

    try:
        print("5. Formatting 5,000 records as POLYGON geometries for bulk insertion...")
        valid_columns = set(PFZZone.__table__.columns.keys())
        objects = []

        for _, row in df.iterrows():
            record = {}

            # Primary Key ID
            if 'id' in row and pd.notna(row['id']):
                record['id'] = str(row['id'])
            else:
                record['id'] = str(uuid.uuid4())

            # Score
            if 'score' in row and pd.notna(row['score']):
                record['score'] = float(row['score'])
            else:
                record['score'] = 1.0

            # Valid Time
            if 'valid_time' in row and pd.notna(row['valid_time']):
                record['valid_time'] = pd.to_datetime(row['valid_time'])
            else:
                record['valid_time'] = datetime.now(timezone.utc)

            # Components (JSONB)
            if 'components' in row and pd.notna(row['components']):
                comp = row['components']
                if isinstance(comp, str):
                    try:
                        record['components'] = json.loads(comp)
                    except Exception:
                        record['components'] = {"raw": comp}
                elif isinstance(comp, dict):
                    record['components'] = comp
                else:
                    record['components'] = {}
            else:
                record['components'] = {}

            # Geometry Column Handling (Ensuring Polygon Output)
            geom_val = row.get('geometry', None)
            lat = row.get('latitude', row.get('lat', None))
            lon = row.get('longitude', row.get('lon', row.get('lng', None)))

            polygon_wkt = parse_geometry_to_polygon(geom_val, lat, lon)
            record['geometry'] = WKTElement(polygon_wkt, srid=4326)

            # Keep only valid model attributes
            final_record = {k: v for k, v in record.items() if k in valid_columns}
            objects.append(PFZZone(**final_record))

        print(f"6. Bulk inserting {len(objects)} records into 'pfz_zones' table...")
        session.bulk_save_objects(objects)
        session.commit()

        print("\n==================================================")
        print("SUCCESS: 5,000 PFZ records successfully seeded into Render DB!")
        print("==================================================")

    except Exception as e:
        session.rollback()
        print(f"\nFAILED to seed database: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()

if __name__ == "__main__":
    file_path = sys.argv[1] if len(sys.argv) > 1 else "pfz_data/PFZ_Hackathon_Synthetic_Dataset_5000.xlsx"
    seed_database(file_path)