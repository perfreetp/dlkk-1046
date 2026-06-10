import random
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
import jellyfish

from .models import Pet, NameEntry, GenerationParams, GenerationRecord


class NameGenerator:
    def __init__(self, name_library: List[NameEntry]):
        self.name_library = name_library

    def _match_pet(self, name: NameEntry, pet: Pet, params: GenerationParams) -> float:
        score = 0.0

        if pet.species and name.species:
            if pet.species.lower() in [s.lower() for s in name.species]:
                score += 3.0

        if pet.gender and name.gender:
            if pet.gender.lower() in [g.lower() for g in name.gender]:
                score += 2.0
            elif "neutral" in [g.lower() for g in name.gender]:
                score += 1.0

        if pet.age_months is not None:
            if name.min_age_months is not None and pet.age_months < name.min_age_months:
                return 0.0
            if name.max_age_months is not None and pet.age_months > name.max_age_months:
                return 0.0
            if name.min_age_months is None and name.max_age_months is None:
                score += 0.5
            else:
                score += 1.0

        if pet.coat_color and name.coat_colors:
            if pet.coat_color.lower() in [c.lower() for c in name.coat_colors]:
                score += 2.0

        if pet.personality and name.personality:
            pet_traits = set(t.lower() for t in pet.personality)
            name_traits = set(t.lower() for t in name.personality)
            matches = pet_traits & name_traits
            if matches:
                score += len(matches) * 1.5

        if params.language and name.language:
            if params.language.lower() == name.language.lower():
                score += 2.0

        if params.style and name.style:
            if params.style.lower() == name.style.lower():
                score += 2.0

        score += name.popularity * 0.1

        return score

    def _filter_names(
        self,
        names: List[NameEntry],
        params: GenerationParams,
        used_names: List[str],
        existing_candidates: List[str],
    ) -> List[NameEntry]:
        filtered = []
        used_set = set(n.lower() for n in used_names)
        existing_set = set(n.lower() for n in existing_candidates)

        for name in names:
            if params.min_length and len(name.name) < params.min_length:
                continue
            if params.max_length and len(name.name) > params.max_length:
                continue

            name_lower = name.name.lower()
            if name_lower in used_set:
                continue
            if name_lower in existing_set:
                continue

            forbidden = False
            for word in params.forbidden_words:
                if word.lower() in name_lower:
                    forbidden = True
                    break
            if forbidden:
                continue

            filtered.append(name)

        return filtered

    def _check_similar(self, name: str, existing_names: List[str], threshold: float = 0.85) -> bool:
        name_lower = name.lower()
        for existing in existing_names:
            existing_lower = existing.lower()
            similarity = jellyfish.jaro_winkler_similarity(name_lower, existing_lower)
            if similarity >= threshold:
                return True
            if jellyfish.soundex(name_lower) == jellyfish.soundex(existing_lower):
                return True
        return False

    def generate_for_pet(
        self,
        pet: Pet,
        params: GenerationParams,
        used_names: List[str],
        count: int = 5,
    ) -> List[str]:
        pet_params = self._merge_params(pet, params)

        scored = []
        for name in self.name_library:
            score = self._match_pet(name, pet, pet_params)
            if score > 0:
                scored.append((name, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        filtered = self._filter_names(
            [n for n, _ in scored],
            pet_params,
            used_names,
            pet.candidate_names + pet.favorite_names,
        )

        selected = []
        existing_all = used_names + pet.candidate_names + pet.favorite_names + selected

        for name in filtered:
            if len(selected) >= count:
                break
            if params.avoid_similar and self._check_similar(name.name, existing_all):
                continue
            selected.append(name.name)
            existing_all.append(name.name)

        if len(selected) < count:
            backup = [n for n, _ in scored if n.name not in selected and n.name not in used_names]
            for name in backup:
                if len(selected) >= count:
                    break
                if name.name not in [s for s in selected]:
                    if params.avoid_similar and self._check_similar(name.name, existing_all):
                        continue
                    selected.append(name.name)
                    existing_all.append(name.name)

        return selected

    def _merge_params(self, pet: Pet, params: GenerationParams) -> GenerationParams:
        merged = GenerationParams()

        merged.species = params.species or pet.species
        merged.gender = params.gender or pet.gender
        merged.coat_color = params.coat_color or pet.coat_color
        merged.personality = params.personality or pet.personality
        merged.batch = params.batch or pet.batch
        merged.min_length = params.min_length
        merged.max_length = params.max_length
        merged.language = params.language
        merged.style = params.style
        merged.forbidden_words = params.forbidden_words
        merged.candidates_per_pet = params.candidates_per_pet
        merged.exclude_used = params.exclude_used
        merged.avoid_similar = params.avoid_similar

        if params.age_min_months is not None:
            merged.age_min_months = params.age_min_months
        elif pet.age_months is not None:
            merged.age_min_months = max(0, pet.age_months - 3)

        if params.age_max_months is not None:
            merged.age_max_months = params.age_max_months
        elif pet.age_months is not None:
            merged.age_max_months = pet.age_months + 12

        return merged

    def generate_batch(
        self,
        pets: List[Pet],
        params: GenerationParams,
        used_names: List[str],
    ) -> Tuple[Dict[str, List[str]], GenerationRecord]:
        results = {}
        all_used = used_names.copy()

        for pet in pets:
            if params.batch and pet.batch != params.batch:
                continue

            candidates = self.generate_for_pet(
                pet,
                params,
                all_used if params.exclude_used else [],
                params.candidates_per_pet,
            )
            results[pet.id] = candidates
            all_used.extend(candidates)

        record = GenerationRecord(
            id=str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            params=params,
            pet_ids=[p.id for p in pets if (not params.batch) or p.batch == params.batch],
            generated_names=results,
        )

        return results, record

    def find_duplicates(self, names: List[str]) -> Dict[str, List[str]]:
        seen = defaultdict(list)
        for name in names:
            seen[name.lower()].append(name)
        return {k: v for k, v in seen.items() if len(v) > 1}

    def find_similar(
        self,
        names: List[str],
        threshold: float = 0.85,
    ) -> List[Tuple[str, str, float]]:
        similar = []
        for i, name1 in enumerate(names):
            for name2 in names[i + 1 :]:
                similarity = jellyfish.jaro_winkler_similarity(name1.lower(), name2.lower())
                if similarity >= threshold:
                    similar.append((name1, name2, similarity))
                elif jellyfish.soundex(name1.lower()) == jellyfish.soundex(name2.lower()):
                    similar.append((name1, name2, similarity))
        return similar

    def get_name_info(self, name_str: str) -> Optional[NameEntry]:
        for name in self.name_library:
            if name.name.lower() == name_str.lower():
                return name
        return None
