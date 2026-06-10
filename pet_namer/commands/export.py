import click
import json
import csv
from pathlib import Path
from tabulate import tabulate
from typing import List

from ..models import Pet
from ..generator import NameGenerator
from ..cli import pass_storage


SPECIES_CN = {
    "cat": "猫咪",
    "dog": "狗狗",
    "rabbit": "兔子",
}

GENDER_CN = {
    "male": "男孩",
    "female": "女孩",
    "neutral": "中性",
}


@click.command()
@click.option("--format", "fmt",
              type=click.Choice(["poster", "csv", "json", "excel", "list"]),
              default="poster", help="导出格式")
@click.option("--output", "-o", help="输出文件路径")
@click.option("--pet-id", "pet_ids", multiple=True, help="指定宠物ID，可多次指定")
@click.option("--batch", help="按批次筛选")
@click.option("--species", type=click.Choice(["cat", "dog", "rabbit", "all"]), default="all", help="按物种筛选")
@click.option("--named-only/--all-pets", default=False, help="只导出名有名字的宠物")
@click.option("--include-candidates/--no-include-candidates", default=False, help="包含候选名字")
@click.option("--include-favorites/--no-include-favorites", default=False, help="包含收藏名字")
@pass_storage
def export(storage, fmt, output, pet_ids, batch, species, named_only,
           include_candidates, include_favorites):
    """导出领养海报名单或数据文件"""
    
    pets = storage.load_pets()
    
    if pet_ids:
        pets = [p for p in pets if p.id in pet_ids]
    
    if batch:
        pets = [p for p in pets if p.batch == batch]
    
    if species and species != "all":
        pets = [p for p in pets if p.species == species]
    
    if named_only:
        pets = [p for p in pets if p.selected_name]
    
    if not pets:
        raise click.ClickException("没有找到符合条件的宠物")
    
    if fmt == "list":
        _export_list(pets, include_candidates, include_favorites)
        return
    
    if fmt == "poster":
        content = _generate_poster(pets, include_candidates, include_favorites)
    elif fmt == "csv":
        content = _generate_csv(pets, include_candidates, include_favorites)
    elif fmt == "json":
        content = _generate_json(pets, include_candidates, include_favorites)
    elif fmt == "excel":
        if not output:
            output = "adoption_list.xlsx"
        _generate_excel(storage, pets, output, include_candidates, include_favorites)
        click.echo(click.style(f"\n已导出到 {output}", fg="green"))
        return
    
    if output:
        output_path = Path(output)
        output_path.write_text(content, encoding="utf-8")
        click.echo(click.style(f"\n已导出到 {output_path}", fg="green"))
    else:
        click.echo()
        click.echo(content)
        click.echo()
        click.echo("使用 -o filename 保存到文件")


def _export_list(pets: List[Pet], include_candidates: bool, include_favorites: bool):
    name_library = []
    try:
        from ..storage import Storage
        s = Storage()
        name_library = s.load_names()
    except:
        pass
    generator = NameGenerator(name_library)
    
    table_data = []
    for pet in pets:
        species = SPECIES_CN.get(pet.species, pet.species)
        gender = GENDER_CN.get(pet.gender, pet.gender or "-")
        age = pet.age or "-"
        color = pet.coat_color or "-"
        personality = ", ".join(pet.personality) if pet.personality else "-"
        
        selected = pet.selected_name or click.style("(未命名)", fg="red")
        
        info = [pet.id[:8], species, gender, age, color, personality, selected]
        
        if include_favorites and pet.favorite_names:
            info.append(", ".join(pet.favorite_names))
        if include_candidates and pet.candidate_names:
            info.append(", ".join(pet.candidate_names))
        
        table_data.append(info)
    
    headers = ["ID", "物种", "性别", "年龄", "毛色", "性格", "正式名"]
    if include_favorites:
        headers.append("收藏名")
    if include_candidates:
        headers.append("候选名")
    
    click.echo(click.style("=== 宠物列表 ===", fg="cyan", bold=True))
    click.echo(tabulate(table_data, headers=headers, tablefmt="simple"))
    click.echo()
    click.echo(f"共 {len(pets)} 只宠物，{sum(1 for p in pets if p.selected_name)} 只已命名")


def _generate_poster(pets: List[Pet], include_candidates: bool, include_favorites: bool) -> str:
    lines = []
    
    title = "🐾 待领养宠物名单 🐾"
    lines.append("=" * 60)
    lines.append(f"{title:^60}")
    lines.append("=" * 60)
    lines.append("")
    
    if len(pets) == 1:
        lines.append(_generate_single_poster(pets[0], include_candidates, include_favorites))
    else:
        for i, pet in enumerate(pets, 1):
            lines.append(f"【第 {i} 号】")
            lines.append("-" * 40)
            lines.append(_generate_single_poster(pet, include_candidates, include_favorites))
            lines.append("")
        
        lines.append("=" * 60)
        lines.append(f"共 {len(pets)} 只萌宠等待温暖的家")
        lines.append("💕 领养代替购买，用爱温暖生命 💕")
        lines.append("=" * 60)
    
    return "\n".join(lines)


def _generate_single_poster(pet: Pet, include_candidates: bool, include_favorites: bool) -> str:
    lines = []
    
    species = SPECIES_CN.get(pet.species, pet.species)
    gender = GENDER_CN.get(pet.gender, pet.gender or "未知")
    age = pet.age or "年龄不详"
    color = pet.coat_color or "毛色不详"
    personality = ", ".join(pet.personality) if pet.personality else "性格温顺"
    
    emoji = "🐱" if pet.species == "cat" else "🐶" if pet.species == "dog" else "🐰"
    
    if pet.selected_name:
        lines.append(f"{emoji} 名字: {click.style(pet.selected_name, fg='green', bold=True)}")
    else:
        lines.append(f"{emoji} 名字: {click.style('待命名', fg='red')}")
    
    lines.append(f"   物种: {species}")
    lines.append(f"   性别: {gender}")
    lines.append(f"   年龄: {age}")
    lines.append(f"   毛色: {color}")
    lines.append(f"   性格: {personality}")
    
    if pet.batch:
        lines.append(f"   批次: {pet.batch}")
    
    if include_favorites and pet.favorite_names:
        favs = "、".join(pet.favorite_names)
        lines.append(f"   ★ 备选: {favs}")
    
    if include_candidates and pet.candidate_names:
        cands = "、".join(pet.candidate_names)
        lines.append(f"   ○ 候选: {cands}")
    
    if pet.notes:
        lines.append(f"   备注: {pet.notes}")
    
    lines.append("")
    lines.append("   💕 如果您对我感兴趣，请联系救助站 💕")
    
    return "\n".join(lines)


def _generate_csv(pets: List[Pet], include_candidates: bool, include_favorites: bool) -> str:
    import io
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    headers = ["ID", "物种", "性别", "年龄", "月龄", "毛色", "性格", "批次", "来源", "正式名"]
    if include_favorites:
        headers.append("收藏名")
    if include_candidates:
        headers.append("候选名")
    headers.append("备注")
    
    writer.writerow(headers)
    
    for pet in pets:
        row = [
            pet.id,
            SPECIES_CN.get(pet.species, pet.species),
            GENDER_CN.get(pet.gender, pet.gender or ""),
            pet.age or "",
            pet.age_months or "",
            pet.coat_color or "",
            "、".join(pet.personality),
            pet.batch or "",
            pet.source or "",
            pet.selected_name or "",
        ]
        if include_favorites:
            row.append("、".join(pet.favorite_names))
        if include_candidates:
            row.append("、".join(pet.candidate_names))
        row.append(pet.notes or "")
        
        writer.writerow(row)
    
    return output.getvalue()


def _generate_json(pets: List[Pet], include_candidates: bool, include_favorites: bool) -> str:
    data = []
    for pet in pets:
        item = {
            "id": pet.id,
            "species": pet.species,
            "species_cn": SPECIES_CN.get(pet.species, pet.species),
            "gender": pet.gender,
            "gender_cn": GENDER_CN.get(pet.gender, pet.gender or ""),
            "age": pet.age,
            "age_months": pet.age_months,
            "coat_color": pet.coat_color,
            "personality": pet.personality,
            "batch": pet.batch,
            "source": pet.source,
            "selected_name": pet.selected_name,
            "notes": pet.notes,
            "created_at": pet.created_at,
        }
        if include_favorites:
            item["favorite_names"] = pet.favorite_names
        if include_candidates:
            item["candidate_names"] = pet.candidate_names
        data.append(item)
    
    return json.dumps(data, ensure_ascii=False, indent=2)


def _generate_excel(storage, pets: List[Pet], output: str, include_candidates: bool, include_favorites: bool):
    import pandas as pd
    
    rows = []
    for pet in pets:
        row = {
            "ID": pet.id,
            "物种": SPECIES_CN.get(pet.species, pet.species),
            "性别": GENDER_CN.get(pet.gender, pet.gender or ""),
            "年龄": pet.age or "",
            "月龄": pet.age_months or "",
            "毛色": pet.coat_color or "",
            "性格": "、".join(pet.personality),
            "批次": pet.batch or "",
            "来源": pet.source or "",
            "正式名": pet.selected_name or "",
            "备注": pet.notes or "",
        }
        if include_favorites:
            row["收藏名"] = "、".join(pet.favorite_names)
        if include_candidates:
            row["候选名"] = "、".join(pet.candidate_names)
        rows.append(row)
    
    df = pd.DataFrame(rows)
    
    try:
        df.to_excel(output, index=False, engine="openpyxl")
    except ImportError:
        raise click.ClickException("需要安装 openpyxl: pip install openpyxl")
