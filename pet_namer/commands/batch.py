import click
import json
import uuid
from pathlib import Path
from tabulate import tabulate
from typing import List, Tuple, Dict

from ..models import Pet, GenerationParams, GenerationRecord, NameEntry
from ..generator import NameGenerator
from ..cli import pass_storage
from .export import (
    _generate_poster, _generate_csv, _generate_json, _generate_excel,
    _load_template, SPECIES_CN, GENDER_CN,
)


AGE_MAP = {
    "幼年": 6, "青年": 18, "成年": 36, "老年": 84,
    "puppy": 6, "kitten": 6, "adult": 36, "senior": 84, "young": 12,
}

SPECIES_MAP = {
    "猫": "cat", "狗": "dog", "兔": "rabbit",
    "猫咪": "cat", "狗狗": "dog", "兔子": "rabbit",
    "cat": "cat", "dog": "dog", "rabbit": "rabbit",
}

GENDER_MAP = {
    "公": "male", "母": "female", "男": "male", "女": "female",
    "male": "male", "female": "female", "中性": "neutral", "unknown": "neutral",
}


def _normalize_species(val):
    if not val:
        return None
    return SPECIES_MAP.get(str(val).strip().lower(), str(val).strip().lower())


def _normalize_gender(val):
    if not val:
        return None
    val = str(val).strip()
    return GENDER_MAP.get(val.lower(), val)


def _parse_age(age_raw, age_months_raw=None):
    import re
    age = None
    age_months = None
    
    if age_months_raw:
        try:
            age_months = int(str(age_months_raw).strip())
        except (ValueError, TypeError):
            age_months = None
    
    if age_raw:
        age_str = str(age_raw).strip()
        if age_str in AGE_MAP:
            age = age_str
            if not age_months:
                age_months = AGE_MAP[age_str]
        else:
            low = age_str.lower()
            m = re.match(r"(\d+)\s*(month|months|m)", low)
            if m:
                age_months = int(m.group(1))
            else:
                m = re.match(r"(\d+)\s*(year|years|y)", low)
                if m:
                    age_months = int(m.group(1)) * 12
                else:
                    m = re.match(r"(\d+)\s*岁", age_str)
                    if m:
                        age_months = int(m.group(1)) * 12
                    else:
                        m = re.match(r"(\d+)\s*个月", age_str)
                        if m:
                            age_months = int(m.group(1))
            
            if age_months is not None:
                if age_months <= 12:
                    age = "幼年"
                elif age_months <= 24:
                    age = "青年"
                elif age_months <= 84:
                    age = "成年"
                else:
                    age = "老年"
    
    return age, age_months


RECOMMEND_LABELS = {
    "top_score": "按匹配度最高",
    "cute_first": "优先可爱风",
    "short_first": "优先短名字",
    "zh_first": "优先中文",
    "en_first": "优先英文",
}


@click.command()
@click.option("--import-file", "-i", "import_file", type=click.Path(exists=True),
              help="从 CSV/Excel 文件导入宠物信息")
@click.option("--batch", "batch_name", help="本次导入的批次号，不指定则从文件读取或自动生成")
@click.option("--count", type=int, default=5, help="每只宠物生成候选名数量")
@click.option("--style", type=click.Choice(["cute", "traditional", "western", "cool", "literary", "all"]),
              default="all", help="名字风格")
@click.option("--language", type=click.Choice(["zh", "en", "all"]), default="all", help="语言")
@click.option("--species", type=click.Choice(["cat", "dog", "rabbit", "all"]), default="all",
              help="按物种筛选（不导入时使用）")
@click.option("--recommend", type=click.Choice(list(RECOMMEND_LABELS.keys())),
              default="top_score", help="自动挑选推荐名的规则")
@click.option("--auto-select/--no-auto-select", default=False,
              help="是否自动将推荐名设为正式名")
@click.option("--export-format", "export_fmt",
              type=click.Choice(["poster", "csv", "json", "excel", "none"]),
              default="poster", help="导出格式，none 表示不导出")
@click.option("--output", "-o", help="导出文件路径")
@click.option("--named-only/--all-pets", default=False, help="导出时只包含已命名宠物")
@click.option("--group-by-species/--no-group-by-species", default=False, help="导出时按物种分组")
@click.option("--include-candidates/--no-include-candidates", default=False, help="导出时包含候选名")
@click.option("--include-favorites/--no-include-favorites", default=False, help="导出时包含收藏名")
@click.option("--contact-phone", help="联系电话（导出模板字段）")
@click.option("--location", help="领养地点（导出模板字段）")
@click.option("--event-date", help="活动日期（导出模板字段）")
@click.option("--event-name", help="活动名称（导出模板字段）")
@click.option("--template", help="模板配置文件（YAML/JSON）")
@click.option("--yes", "-y", is_flag=True, help="跳过所有确认步骤")
@pass_storage
def batch(storage, import_file, batch_name, count, style, language, species,
          recommend, auto_select, export_fmt, output, named_only, group_by_species,
          include_candidates, include_favorites, contact_phone, location,
          event_date, event_name, template, yes):
    """批量任务模式：导入→生成候选→自动推荐→导出海报"""
    
    template_data = _load_template(template)
    template_data["contact_phone"] = contact_phone or template_data.get("contact_phone", "")
    template_data["location"] = location or template_data.get("location", "")
    template_data["event_date"] = event_date or template_data.get("event_date", "")
    template_data["event_name"] = event_name or template_data.get("event_name", "")
    
    click.echo(click.style("=" * 60, fg="cyan", bold=True))
    click.echo(click.style("🐾 宠物批量起名任务 🐾", fg="cyan", bold=True))
    click.echo(click.style("=" * 60, fg="cyan", bold=True))
    click.echo()
    
    target_pets = []
    
    # ===== Step 1: Import =====
    if import_file:
        click.echo(click.style("【步骤 1/4】导入宠物信息", fg="yellow", bold=True))
        imported_pets = _batch_import(storage, import_file, batch_name, yes)
        target_pets = imported_pets
        click.echo()
    else:
        click.echo(click.style("【步骤 1/4】选择目标宠物", fg="yellow", bold=True))
        pets = storage.load_pets()
        if species and species != "all":
            pets = [p for p in pets if p.species == species]
        if not pets:
            raise click.ClickException("没有符合条件的宠物，请先使用 --import-file 导入")
        target_pets = pets
        click.echo(f"  已选择 {len(target_pets)} 只宠物（物种筛选: {species}）")
        click.echo()
    
    if not target_pets:
        raise click.ClickException("没有可处理的宠物")
    
    # ===== Step 2: Generate =====
    click.echo(click.style("【步骤 2/4】生成候选名字", fg="yellow", bold=True))
    params = GenerationParams(
        candidates_per_pet=count,
        style=None if style == "all" else style,
        language=None if language == "all" else language,
        avoid_similar=True,
        exclude_used=True,
    )
    
    results, generated_pets, failed_pets = _batch_generate(
        storage, target_pets, params
    )
    click.echo()
    
    # ===== Step 3: Recommend =====
    click.echo(click.style("【步骤 3/4】自动挑选推荐名", fg="yellow", bold=True))
    name_library = storage.load_names()
    recommendations = _batch_recommend(
        storage, generated_pets, results, name_library, recommend, auto_select
    )
    click.echo()
    
    # ===== Step 4: Export =====
    export_result = None
    if export_fmt != "none":
        click.echo(click.style("【步骤 4/4】导出领养名单", fg="yellow", bold=True))
        export_pets = generated_pets
        if named_only:
            export_pets = [p for p in export_pets if p.selected_name]
        
        export_result = _batch_export(
            storage, export_pets, export_fmt, output, include_candidates,
            include_favorites, group_by_species, template_data
        )
        click.echo()
    
    # ===== Summary =====
    click.echo(click.style("=" * 60, fg="cyan", bold=True))
    click.echo(click.style("📊 任务总结", fg="yellow", bold=True))
    
    summary = [
        ["目标宠物总数", len(target_pets)],
        ["成功生成候选名", len(generated_pets)],
        ["生成失败", len(failed_pets)],
        ["推荐规则", RECOMMEND_LABELS.get(recommend, recommend)],
        ["自动设为正式名", "✅ 已启用" if auto_select else "仅推荐未设置"],
        ["推荐成功数", len([r for r in recommendations if r["recommended"]])],
    ]
    if export_result:
        summary.append(["导出格式", export_fmt])
        summary.append(["导出文件", export_result])
    
    click.echo(tabulate(summary, tablefmt="simple"))
    
    if failed_pets:
        click.echo()
        click.echo(click.style("⚠️  生成失败的宠物:", fg="yellow"))
        for pid, reason in failed_pets:
            click.echo(f"  - {pid[:8]}: {reason}")
    
    click.echo()
    click.echo(click.style("✅ 批量任务完成！", fg="green", bold=True))


def _batch_import(storage, import_file: str, batch_name: str, skip_confirm: bool) -> List[Pet]:
    path = Path(import_file)
    
    try:
        import pandas as pd
        if path.suffix.lower() in [".xlsx", ".xls"]:
            df = pd.read_excel(path)
        else:
            df = pd.read_csv(path, encoding_errors="replace")
    except Exception as e:
        raise click.ClickException(f"读取文件失败: {e}")
    
    click.echo(f"  读取文件: {path}")
    click.echo(f"  读取到 {len(df)} 行数据")
    click.echo(f"  列名: {', '.join(df.columns.tolist())}")
    
    pets = []
    
    def _get_value(row, *keys):
        if len(keys) == 1 and isinstance(keys[0], (list, tuple)):
            keys = keys[0]
        for key in keys:
            if key in row and row[key] is not None and str(row[key]).strip():
                return str(row[key]).strip()
        return None
    
    for _, row in df.iterrows():
        species = _normalize_species(_get_value(row, "物种", "species", "品种"))
        gender = _normalize_gender(_get_value(row, "性别", "gender", "sex"))
        age_raw = _get_value(row, "年龄", "age")
        age_months_raw = _get_value(row, "月龄", "age_months", "month")
        
        age, age_months = _parse_age(age_raw, age_months_raw)
        coat_color = _get_value(row, "毛色", "coat_color", "颜色", "color")
        personality_raw = _get_value(row, "性格", "personality", "trait")
        personality = []
        if personality_raw:
            personality = [p.strip() for p in personality_raw.replace("，", ",").split(",") if p.strip()]
        
        source_batch = _get_value(row, "批次", "batch")
        source = _get_value(row, "来源", "source", "origin")
        notes = _get_value(row, "备注", "notes", "remark")
        
        if batch_name and not source_batch:
            source_batch = batch_name
        
        pet = Pet(
            id=uuid.uuid4().hex[:8],
            species=species,
            gender=gender,
            age=age,
            age_months=age_months,
            coat_color=coat_color,
            personality=personality,
            batch=source_batch or batch_name,
            source=source,
            notes=notes,
            candidate_names=[],
            favorite_names=[],
        )
        pets.append(pet)
    
    # Preview
    click.echo()
    click.echo(click.style("  === 预览导入数据 ===", fg="cyan"))
    table_data = []
    for i, pet in enumerate(pets, 1):
        info_parts = [pet.species or "-", pet.gender or "-", pet.age or "-"]
        if pet.coat_color:
            info_parts.append(pet.coat_color)
        if pet.personality:
            info_parts.append(",".join(pet.personality))
        info = " | ".join(info_parts)
        table_data.append([i, pet.id[:8], info, pet.selected_name or "-"])
    
    click.echo(tabulate(
        table_data,
        headers=["#", "ID", "信息", "已有名字"],
        tablefmt="simple"
    ))
    
    if not skip_confirm and not click.confirm(f"\n  确认导入 {len(pets)} 只宠物？", default=True):
        raise click.ClickException("已取消导入")
    
    imported = []
    for pet in pets:
        storage.add_pet(pet)
        imported.append(pet)
    
    click.echo(click.style(f"  ✅ 成功导入 {len(imported)} 只宠物！", fg="green"))
    return imported


def _batch_generate(storage, pets: List[Pet], params: GenerationParams) -> Tuple[
    Dict[str, List[str]], List[Pet], List[Tuple[str, str]]
]:
    name_library = storage.load_names()
    generator = NameGenerator(name_library)
    used_names = set(storage.get_used_names())
    
    results = {}
    generated_pets = []
    failed = []
    
    total = len(pets)
    
    for i, pet in enumerate(pets, 1):
        progress = f"[{i}/{total}]"
        pet_label = f"{pet.id[:8]} ({pet.species or '?'})"
        try:
            current_used = list(used_names)
            candidates = generator.generate_for_pet(pet, params, current_used, params.candidates_per_pet)
            
            if candidates:
                pet.candidate_names = candidates
                storage.update_pet(pet)
                used_names.update(candidates)
                results[pet.id] = candidates
                generated_pets.append(pet)
                sample = ", ".join(candidates[:3]) + ("..." if len(candidates) > 3 else "")
                click.echo(f"  ✅ {progress} {pet_label}: {sample}")
            else:
                failed.append((pet.id, "未找到合适候选名"))
                click.echo(f"  ⚠️  {progress} {pet_label}: 未找到合适候选名")
        except Exception as e:
            failed.append((pet.id, str(e)))
            click.echo(f"  ❌ {progress} {pet_label}: 生成失败 - {e}")
    
    # Record generation
    record = GenerationRecord(
        id=uuid.uuid4().hex[:12],
        timestamp=__import__("datetime").datetime.now().isoformat(),
        params=params,
        pet_ids=[p.id for p in generated_pets],
        generated_names=results,
    )
    storage.add_record(record)
    
    stats = storage.load_stats()
    stats.generation_count += 1
    stats.named_pets = sum(1 for p in storage.load_pets() if p.selected_name)
    storage.save_stats(stats)
    
    click.echo()
    click.echo(f"  生成记录ID: {record.id}")
    click.echo(click.style(
        f"  完成: 成功 {len(generated_pets)}/{total}, 失败 {len(failed)}",
        fg="green" if not failed else "yellow"
    ))
    
    return results, generated_pets, failed


def _batch_recommend(storage, pets: List[Pet], results: Dict[str, List[str]],
                     name_library: List[NameEntry], strategy: str,
                     auto_select: bool) -> List[dict]:
    name_info_map = {}
    for ne in name_library:
        name_info_map[ne.name.lower()] = ne
    
    recommendations = []
    total = len(pets)
    
    for i, pet in enumerate(pets, 1):
        progress = f"[{i}/{total}]"
        candidates = results.get(pet.id, pet.candidate_names)
        if not candidates:
            recommendations.append({"pet_id": pet.id, "recommended": None})
            click.echo(f"  ⚠️  {progress} {pet.id[:8]}: 无候选名可推荐")
            continue
        
        scored = []
        for name in candidates:
            info = name_info_map.get(name.lower())
            score = 0
            
            if strategy == "top_score":
                score = candidates.index(name) * -10 + 100
            elif strategy == "cute_first":
                if info and info.style == "cute":
                    score += 100
                score += (len(candidates) - candidates.index(name)) * 5
            elif strategy == "short_first":
                score += (20 - len(name)) * 10
                score += (len(candidates) - candidates.index(name)) * 2
            elif strategy == "zh_first":
                if info and info.language == "zh":
                    score += 100
                score += (len(candidates) - candidates.index(name)) * 5
            elif strategy == "en_first":
                if info and info.language == "en":
                    score += 100
                score += (len(candidates) - candidates.index(name)) * 5
            
            scored.append((name, score, info))
        
        scored.sort(key=lambda x: -x[1])
        best_name, best_score, best_info = scored[0]
        
        style_label = best_info.style if best_info else "-"
        lang_label = best_info.language if best_info else "-"
        
        if auto_select:
            pet.selected_name = best_name
            if best_name not in pet.favorite_names:
                pet.favorite_names.append(best_name)
            storage.update_pet(pet)
            status = "✅ 已设为正式名"
        else:
            status = "📌 推荐"
        
        recommendations.append({"pet_id": pet.id, "recommended": best_name})
        click.echo(f"  {progress} {pet.id[:8]}: {status} → {best_name} ({lang_label}/{style_label})")
    
    success = sum(1 for r in recommendations if r["recommended"])
    click.echo()
    click.echo(click.style(f"  推荐完成: {success}/{total} 只", fg="green"))
    
    stats = storage.load_stats()
    stats.named_pets = sum(1 for p in storage.load_pets() if p.selected_name)
    storage.save_stats(stats)
    
    return recommendations


def _batch_export(storage, pets: List[Pet], fmt: str, output: str,
                  include_candidates: bool, include_favorites: bool,
                  group_by_species: bool, template_data: dict) -> str:
    if not pets:
        click.echo("  ⚠️  没有可导出的宠物")
        return ""
    
    default_outputs = {
        "poster": "adoption_poster.txt",
        "csv": "adoption_list.csv",
        "json": "adoption_list.json",
        "excel": "adoption_list.xlsx",
    }
    
    if not output:
        output = default_outputs.get(fmt, "adoption_output")
    
    if fmt == "poster":
        content = _generate_poster(pets, include_candidates, include_favorites, group_by_species, template_data)
        Path(output).write_text(content, encoding="utf-8")
    elif fmt == "csv":
        content = _generate_csv(pets, include_candidates, include_favorites, template_data)
        Path(output).write_text(content, encoding="utf-8")
    elif fmt == "json":
        content = _generate_json(pets, include_candidates, include_favorites, template_data)
        Path(output).write_text(content, encoding="utf-8")
    elif fmt == "excel":
        _generate_excel(storage, pets, output, include_candidates, include_favorites, template_data)
    
    click.echo(click.style(f"  ✅ 已导出 {len(pets)} 只宠物到: {output}", fg="green"))
    return output
