from app.schemas.layers import LayerOut


def get_available_layers() -> list[LayerOut]:
    return [
        LayerOut(
            id="observations",
            name="Marine Observations",
            type="observation",
            source="incois,mosdac,imd",
            valid_time=None,
            visible_default=True,
        ),
        LayerOut(
            id="pfz",
            name="Potential Fishing Zones",
            type="pfz",
            source="incois",
            valid_time=None,
            visible_default=True,
        ),
        LayerOut(
            id="warnings",
            name="Active Warnings",
            type="warning",
            source="imd,incois",
            valid_time=None,
            visible_default=True,
        ),
        LayerOut(
            id="mpa",
            name="MPA Boundaries",
            type="mpa",
            source="moes",
            valid_time=None,
            visible_default=False,
        ),
    ]
