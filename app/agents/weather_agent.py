from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, Optional

from app.agents.base_agent import BaseAgent
from app.connectors.incois_connector import IncoisConnector
from app.schemas.agent import AgentEvidence, AgentResultData
from app.services import observations_service

logger = logging.getLogger("orca")

WHY_IT_MATTERS = {
    "sst": "Sea surface temperature affects fish distribution and storm intensity.",
    "chlorophyll": "Chlorophyll indicates phytoplankton concentration and potential fishing zones.",
    "wave_height": "Wave height directly impacts vessel safety and fishing operations.",
    "wind_speed": "Wind speed affects sea state and vessel handling.",
    "wind_direction": "Wind direction influences wave patterns and drift.",
    "air_temperature": "Air temperature affects crew comfort and equipment performance.",
    "humidity": "Humidity affects weather patterns and storm development.",
}


class WeatherAgent(BaseAgent):
    async def _execute(
        self,
        db,
        lat: float,
        lon: float,
        radius_km: float = 10.0,
        variables: Optional[list[str]] = None,
    ) -> AgentResultData:
        task_id = uuid.uuid4()
        started_at = datetime.utcnow()
        errors: list[str] = []

        observations = []
        source_status = "no_data"

        try:
            observations = await observations_service.get_observations(
                db,
                variable=",".join(variables) if variables else None,
                lat=lat,
                lon=lon,
                radius_km=radius_km,
            )
            if observations:
                source_status = "live"
        except Exception as exc:
            logger.warning("WeatherAgent failed to fetch observations from DB: %s", exc)
            return AgentResultData(
                agent_name=self.name,
                task_id=str(task_id),
                status="unavailable",
                data=None,
                evidence=[],
                errors=[f"observations_service_error: {exc}"],
                started_at=started_at,
                completed_at=datetime.utcnow(),
                duration_ms=0.0,
                source_status="unavailable",
            )

        if not observations:
            connector = IncoisConnector()
            search_result = await connector.search_datasets(
                search_for=variables[0] if variables else "ocean"
            )
            if search_result.status == "success" and search_result.data:
                dataset_info = connector.select_observation_dataset(search_result)
                if dataset_info:
                    query_variables = []
                    for var in (variables or ["TEMP", "PSAL"]):
                        query_variables.append(var.upper() if var.lower() in {"temp", "psal"} else var)
                    if not query_variables:
                        query_variables = ["TEMP", "PSAL"]

                    query_method = connector.query_griddap if dataset_info["access_method"] == "griddap" else connector.query_dataset
                    default_time_min = (datetime.utcnow() - timedelta(days=1095)).strftime("%Y-%m-%d")
                    query_result = await query_method(
                        dataset_id=dataset_info["dataset_id"],
                        variables=query_variables,
                        lat_min=lat - radius_km / 111.0,
                        lat_max=lat + radius_km / 111.0,
                        lon_min=lon - radius_km / 111.0,
                        lon_max=lon + radius_km / 111.0,
                        time_min=default_time_min,
                    )
                    if query_result.status == "success" and query_result.data:
                        normalized = connector.normalize_observations(
                            query_result.data,
                            variable_mapping={"temp": "temperature", "psal": "salinity"},
                        )
                        if normalized.evidence:
                            observations = [
                                SimpleNamespace(**ev.__dict__) for ev in normalized.evidence
                            ]
                            source_status = normalized.source_status
                            errors.extend(normalized.errors)

        if not observations:
            return AgentResultData(
                agent_name=self.name,
                task_id=str(task_id),
                status="no_data",
                data=[],
                evidence=[],
                errors=errors,
                started_at=started_at,
                completed_at=datetime.utcnow(),
                duration_ms=0.0,
                source_status=source_status,
            )

        evidence: list[AgentEvidence] = []
        data: list[dict] = []

        for obs in observations:
            if hasattr(obs, "model_dump"):
                obs_dict = obs.model_dump()
            elif hasattr(obs, "__dict__"):
                obs_dict = vars(obs)
            else:
                obs_dict = dict(obs) if hasattr(obs, "keys") else {}
            variable = (obs_dict.get("variable") or "").lower()
            evidence.append(
                AgentEvidence(
                    source=obs_dict.get("source", "incois"),
                    variable=variable,
                    value=obs_dict.get("value"),
                    unit=obs_dict.get("unit"),
                    valid_time=obs_dict.get("valid_time") or obs_dict.get("observed_at") or obs_dict.get("source_time"),
                    confidence=obs_dict.get("confidence"),
                    why_it_matters=WHY_IT_MATTERS.get(variable),
                )
            )
            data.append(obs_dict)

        completed_at = datetime.utcnow()
        duration_ms = (completed_at - started_at).total_seconds() * 1000

        return AgentResultData(
            agent_name=self.name,
            task_id=str(task_id),
            status="success",
            data=data,
            evidence=evidence,
            errors=errors,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=round(duration_ms, 3),
            source_status=source_status,
        )
