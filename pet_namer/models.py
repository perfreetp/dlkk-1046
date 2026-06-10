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
