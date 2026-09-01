from app.schemas.common import ApiResponse, ErrorCode
from app.schemas.electricity import ElectricityReading


def test_api_response_envelope() -> None:
    result = ApiResponse.ok(["one"])
    assert result.success is True
    assert result.code == ErrorCode.OK
    assert result.data == ["one"]


def test_electricity_reading_preserves_raw_data() -> None:
    reading = ElectricityReading(
        area_id="2",
        building_id="b1",
        floor_id="f2",
        room_id="r3",
        raw_data={"vTotal": "uninterpreted"},
    )
    assert reading.raw_data["vTotal"] == "uninterpreted"
    assert reading.remaining_money is None
