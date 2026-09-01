"""Campus hierarchy models using only API-provided internal identifiers."""

from pydantic import BaseModel


class Campus(BaseModel):
    id: str
    name: str


class Building(BaseModel):
    id: str
    name: str
    area_id: str


class Floor(BaseModel):
    id: str
    name: str
    building_id: str
    area_id: str


class Room(BaseModel):
    id: str
    name: str
    floor_id: str
    building_id: str
    area_id: str
