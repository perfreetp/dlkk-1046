import json
import os
from typing import List, Dict, Optional
from pathlib import Path
from .models import Pet, NameEntry, GenerationRecord, StatsData


class Storage:
    def __init__(self, data_dir: str = ".pet-namer"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)

        self.pets_file = self.data_dir / "pets.json"
        self.names_file = self.data_dir / "names.json"
        self.records_file = self.data_dir / "records.json"
        self.stats_file = self.data_dir / "stats.json"
        self.config_file = self.data_dir / "config.json"

        self._init_files()

    def _init_files(self):
        for file in [self.pets_file, self.names_file, self.records_file]:
            if not file.exists():
                file.write_text(json.dumps([], ensure_ascii=False, indent=2), encoding="utf-8")
        if not self.stats_file.exists():
            self.stats_file.write_text(
                json.dumps(StatsData().to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        if not self.config_file.exists():
            self.config_file.write_text(json.dumps({
                "default_language": "zh",
                "default_style": "cute",
                "forbidden_words": [],
            }, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_pets(self) -> List[Pet]:
        content = self._read_text(self.pets_file)
        data = json.loads(content)
        return [Pet.from_dict(item) for item in data]

    def save_pets(self, pets: List[Pet]):
        self.pets_file.write_text(
            json.dumps([p.to_dict() for p in pets], ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def add_pet(self, pet: Pet) -> Pet:
        pets = self.load_pets()
        pets.append(pet)
        self.save_pets(pets)
        return pet

    def update_pet(self, pet: Pet) -> Optional[Pet]:
        pets = self.load_pets()
        for i, p in enumerate(pets):
            if p.id == pet.id:
                pets[i] = pet
                self.save_pets(pets)
                return pet
        return None

    def get_pet(self, pet_id: str) -> Optional[Pet]:
        pets = self.load_pets()
        for p in pets:
            if p.id == pet_id:
                return p
        return None

    def delete_pet(self, pet_id: str) -> bool:
        pets = self.load_pets()
        pets = [p for p in pets if p.id != pet_id]
        self.save_pets(pets)
        return True

    def load_names(self) -> List[NameEntry]:
        content = self._read_text(self.names_file)
        data = json.loads(content)
        return [NameEntry.from_dict(item) for item in data]

    def save_names(self, names: List[NameEntry]):
        self.names_file.write_text(
            json.dumps([n.to_dict() for n in names], ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def add_name(self, name: NameEntry) -> NameEntry:
        names = self.load_names()
        names.append(name)
        self.save_names(names)
        return name

    def load_records(self) -> List[GenerationRecord]:
        content = self._read_text(self.records_file)
        data = json.loads(content)
        return [GenerationRecord.from_dict(item) for item in data]

    def save_records(self, records: List[GenerationRecord]):
        self.records_file.write_text(
            json.dumps([r.to_dict() for r in records], ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def add_record(self, record: GenerationRecord) -> GenerationRecord:
        records = self.load_records()
        records.append(record)
        self.save_records(records)
        return record

    def get_record(self, record_id: str) -> Optional[GenerationRecord]:
        records = self.load_records()
        for r in records:
            if r.id == record_id:
                return r
        return None

    def load_stats(self) -> StatsData:
        content = self._read_text(self.stats_file)
        data = json.loads(content)
        return StatsData.from_dict(data)

    def save_stats(self, stats: StatsData):
        self.stats_file.write_text(
            json.dumps(stats.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def load_config(self) -> Dict:
        content = self._read_text(self.config_file)
        return json.loads(content)

    def save_config(self, config: Dict):
        self.config_file.write_text(
            json.dumps(config, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def _read_text(self, file_path):
        encodings = ["utf-8", "utf-8-sig", "gbk", "gb2312", "cp1252"]
        for enc in encodings:
            try:
                return file_path.read_text(encoding=enc)
            except UnicodeDecodeError:
                continue
        return file_path.read_text(encoding="utf-8", errors="replace")

    def get_used_names(self) -> List[str]:
        pets = self.load_pets()
        used = []
        for p in pets:
            if p.selected_name:
                used.append(p.selected_name)
            used.extend(p.favorite_names)
        return list(set(used))
