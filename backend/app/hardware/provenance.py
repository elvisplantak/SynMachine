"""Reject nested input keys discarded by domain validation at offline boundaries."""

from collections.abc import Mapping

from pydantic import BaseModel


def reject_lost_keys(raw: object, validated: object) -> None:
    if isinstance(raw, BaseModel):
        raw = {**raw.__dict__, **(raw.model_extra or {})}
    if isinstance(validated, BaseModel):
        validated = {**validated.__dict__, **(validated.model_extra or {})}
    if isinstance(raw, Mapping) and isinstance(validated, Mapping):
        if raw.keys() - validated.keys():
            raise ValueError("source or assumptions lost information during validation")
        for key, value in raw.items():
            reject_lost_keys(value, validated[key])
    elif isinstance(raw, (list, tuple)) and isinstance(validated, (list, tuple)):
        if len(raw) != len(validated):
            raise ValueError("source or assumptions lost information during validation")
        for before, after in zip(raw, validated, strict=True):
            reject_lost_keys(before, after)
