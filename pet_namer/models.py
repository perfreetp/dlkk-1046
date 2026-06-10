from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
import json


@dataclass
class Pet:
    id: str
    species: str
    gender: Optional[str] = None
    age: Optional[str] = None
    age_months: Optional[int] = None
    coat_color: Optional[str] = None
    personality: List[str] = field(default_factory=list)
    batch: Optional[str] = None
    source: Optional[str] = None
    selected_name: Optional[str] = None
    candidate_names: List[str] = field(default_factory=list)
    favorite_names: List[str] = field(default_factory=list)
    notes: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Pet":
        return cls(**data)


@dataclass
class NameEntry:
    name: str
    language: str
    style: str
    species: List[str]
    gender: List[str]
    personality: List[str]
    min_age_months: Optional[int] = None
    max_age_months: Optional[int] = None
    coat_colors: List[str] = field(default_factory=list)
    meaning: Optional[str] = None
    origin: Optional[str] = None
    popularity: int = 5

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NameEntry":
        return cls(**data)


@dataclass
class GenerationParams:
    species: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[str] = None
    age_min_months: Optional[int] = None
    age_max_months: Optional[int] = None
    coat_color: Optional[str] = None
    personality: List[str] = field(default_factory=list)
    batch: Optional[str] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    language: Optional[str] = None
    style: Optional[str] = None
    forbidden_words: List[str] = field(default_factory=list)
    candidates_per_pet: int = 5
    exclude_used: bool = True
    avoid_similar: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GenerationParams":
        return cls(**data)


@dataclass
class GenerationRecord:
    id: str
    timestamp: str
    params: GenerationParams
    pet_ids: List[str]
    generated_names: Dict[str, List[str]]
    selected_names: Dict[str, Optional[str]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "params": self.params.to_dict(),
            "pet_ids": self.pet_ids,
            "generated_names": self.generated_names,
            "selected_names": self.selected_names,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GenerationRecord":
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            params=GenerationParams.from_dict(data["params"]),
            pet_ids=data["pet_ids"],
            generated_names=data["generated_names"],
            selected_names=data.get("selected_names", {}),
        )


@dataclass
class StatsData:
    total_pets: int = 0
    named_pets: int = 0
    style_distribution: Dict[str, int] = field(default_factory=dict)
    language_distribution: Dict[str, int] = field(default_factory=dict)
    favorite_style_distribution: Dict[str, int] = field(default_factory=dict)
    favorite_language_distribution: Dict[str, int] = field(default_factory=dict)
    species_distribution: Dict[str, int] = field(default_factory=dict)
    batch_distribution: Dict[str, int] = field(default_factory=dict)
    top_names: List[tuple] = field(default_factory=list)
    favorite_top_names: List[tuple] = field(default_factory=list)
    generation_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_pets": self.total_pets,
            "named_pets": self.named_pets,
            "style_distribution": self.style_distribution,
            "language_distribution": self.language_distribution,
            "favorite_style_distribution": self.favorite_style_distribution,
            "favorite_language_distribution": self.favorite_language_distribution,
            "species_distribution": self.species_distribution,
            "batch_distribution": self.batch_distribution,
            "top_names": [list(item) for item in self.top_names],
            "favorite_top_names": [list(item) for item in self.favorite_top_names],
            "generation_count": self.generation_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StatsData":
        return cls(
            total_pets=data.get("total_pets", 0),
            named_pets=data.get("named_pets", 0),
            style_distribution=data.get("style_distribution", {}),
            language_distribution=data.get("language_distribution", {}),
            favorite_style_distribution=data.get("favorite_style_distribution", {}),
            favorite_language_distribution=data.get("favorite_language_distribution", {}),
            species_distribution=data.get("species_distribution", {}),
            batch_distribution=data.get("batch_distribution", {}),
            top_names=[tuple(item) for item in data.get("top_names", [])],
            favorite_top_names=[tuple(item) for item in data.get("favorite_top_names", [])],
            generation_count=data.get("generation_count", 0),
        )


@dataclass
class BatchTaskStep:
    name: str
    started_at: str
    finished_at: Optional[str] = None
    total_count: int = 0
    success_count: int = 0
    failed_ids: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_count": self.total_count,
            "success_count": self.success_count,
            "failed_ids": self.failed_ids,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BatchTaskStep":
        return cls(
            name=data["name"],
            started_at=data["started_at"],
            finished_at=data.get("finished_at"),
            total_count=data.get("total_count", 0),
            success_count=data.get("success_count", 0),
            failed_ids=data.get("failed_ids", []),
            extra=data.get("extra", {}),
        )


@dataclass
class AuditLogEntry:
    timestamp: str
    operator: Optional[str]
    action: str
    pet_id: Optional[str] = None
    detail: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "operator": self.operator,
            "action": self.action,
            "pet_id": self.pet_id,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditLogEntry":
        return cls(
            timestamp=data["timestamp"],
            operator=data.get("operator"),
            action=data["action"],
            pet_id=data.get("pet_id"),
            detail=data.get("detail"),
        )


@dataclass
class ReviewEntry:
    pet_id: str
    recommended_name: str
    final_name: Optional[str] = None
    status: str = "pending"
    note: Optional[str] = None
    reviewed_at: Optional[str] = None
    reviewed_by: Optional[str] = None
    history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pet_id": self.pet_id,
            "recommended_name": self.recommended_name,
            "final_name": self.final_name,
            "status": self.status,
            "note": self.note,
            "reviewed_at": self.reviewed_at,
            "reviewed_by": self.reviewed_by,
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReviewEntry":
        return cls(
            pet_id=data["pet_id"],
            recommended_name=data["recommended_name"],
            final_name=data.get("final_name"),
            status=data.get("status", "pending"),
            note=data.get("note"),
            reviewed_at=data.get("reviewed_at"),
            reviewed_by=data.get("reviewed_by"),
            history=data.get("history", []),
        )


TASK_STATUS = [
    "draft",
    "pending_review",
    "review_in_progress",
    "reviewed",
    "export_confirmed",
    "completed",
    "archived",
]

HANDOFF_STATUS = ["not_started", "in_progress", "waiting", "completed", "handed_over"]


@dataclass
class BatchTaskRecord:
    id: str
    timestamp: str
    status: str = "running"
    steps: List[BatchTaskStep] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)
    export_file: Optional[str] = None
    generation_record_id: Optional[str] = None

    owner: Optional[str] = None
    store: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    handoff_status: str = "not_started"
    handoff_to: Optional[str] = None
    export_confirmed: bool = False
    reviews: List[ReviewEntry] = field(default_factory=list)
    audit_log: List[AuditLogEntry] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "status": self.status,
            "steps": [s.to_dict() for s in self.steps],
            "params": self.params,
            "export_file": self.export_file,
            "generation_record_id": self.generation_record_id,
            "owner": self.owner,
            "store": self.store,
            "tags": self.tags,
            "handoff_status": self.handoff_status,
            "handoff_to": self.handoff_to,
            "export_confirmed": self.export_confirmed,
            "reviews": [r.to_dict() for r in self.reviews],
            "audit_log": [a.to_dict() for a in self.audit_log],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BatchTaskRecord":
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            status=data.get("status", "unknown"),
            steps=[BatchTaskStep.from_dict(s) for s in data.get("steps", [])],
            params=data.get("params", {}),
            export_file=data.get("export_file"),
            generation_record_id=data.get("generation_record_id"),
            owner=data.get("owner"),
            store=data.get("store"),
            tags=data.get("tags", []),
            handoff_status=data.get("handoff_status", "not_started"),
            handoff_to=data.get("handoff_to"),
            export_confirmed=data.get("export_confirmed", False),
            reviews=[ReviewEntry.from_dict(r) for r in data.get("reviews", [])],
            audit_log=[AuditLogEntry.from_dict(a) for a in data.get("audit_log", [])],
        )
