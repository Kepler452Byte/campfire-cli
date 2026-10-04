from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Segment(Contract):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def interval(self) -> Segment:
        if self.end <= self.start or not self.text.strip():
            raise ValueError("转写区间必须递增且文字不能为空")
        return self


class Frame(Contract):
    id: str
    path: str
    seconds: float = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Material(Contract):
    schema_version: Literal[1] = 1
    source_name: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    duration: float = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    transcript_source: str
    segments: list[Segment]
    frames: list[Frame]
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def timeline(self) -> Material:
        if any(s.end > self.duration + 0.5 for s in self.segments):
            raise ValueError("转写超出媒体时长")
        if any(a.start > b.start for a, b in zip(self.segments, self.segments[1:], strict=False)):
            raise ValueError("转写必须按时间排序")
        if any(f.seconds > self.duration + 0.5 for f in self.frames):
            raise ValueError("截图超出媒体时长")
        if len({f.id for f in self.frames}) != len(self.frames):
            raise ValueError("截图 ID 重复")
        return self


class Section(Contract):
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)
    segment_ids: list[int] = Field(default_factory=list)
    frame_ids: list[str] = Field(default_factory=list)


class Draft(Contract):
    title: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sections: list[Section] = Field(min_length=1)
    limitations: list[str] = Field(default_factory=list)
    visual_reviewed: bool = False
