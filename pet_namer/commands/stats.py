import click
from collections import Counter, defaultdict
from tabulate import tabulate
from typing import List, Dict

from ..models import Pet, NameEntry, StatsData
from ..generator import NameGenerator
from ..cli import pass_storage


STYLE_CN = {
    "cute": "可爱风",
    "traditional": "传统风",
    "western": "欧美风",
    "cool": "酷炫风",
    "literary": "文艺风",
}

LANGUAGE_CN = {
    "zh": "中文",
    "en": "英文",
}

SPECIES_CN = {
    "cat": "猫咪",
    "dog": "狗狗",
    "rabbit": "兔子",
}


@click.command()
@click.option("--batch", help="按批次统计")
@click.option("--species", type=click.Choice(["cat", "dog", "rabbit", "all"]), default="all", help="按物种统计")
@click.option("--update/--no-update", default=True, help="更新统计数据")
@click.option("--top", type=int, default=10, help="显示最热门名字的数量")
@click.option("--by-style/--no-by-style", default=True, help="显示风格分布")
@click.option("--by-language/--no-by-language", default=True, help="显示语言分布")
@click.option("--by-species/--no-by-species", default=True, help="显示物种分布")
@click.option("--by-batch/--no-by-batch", default=False, help="显示批次分布")
@click.option("--records/--no-records", default=False, help="显示生成记录历史")
@click.option("--output", "-o", help="导出统计结果到JSON文件")
@pass_storage
def stats(storage, batch, species, update, top, by_style, by_language,
          by_species, by_batch, records, output):
    """统计分析不同风格使用比例和使用情况"""
    
    pets = storage.load_pets()
    name_library = storage.load_names()
    generator = NameGenerator(name_library)
    
    if batch:
        pets = [p for p in pets if p.batch == batch]
    
    if species and species != "all":
        pets = [p for p in pets if p.species == species]
    
    if update:
        stats_data = _compute_stats(storage, pets, name_library, top)
        storage.save_stats(stats_data)
    else:
        stats_data = storage.load_stats()
    
    click.echo(click.style("=== 宠物起名统计 ===", fg="cyan", bold=True))
    click.echo()
    
    click.echo(click.style("📊 总体情况", fg="yellow"))
    overall_table = [
        ["宠物总数", stats_data.total_pets],
        ["已命名宠物数", stats_data.named_pets],
        ["命名率", f"{stats_data.named_pets / stats_data.total_pets * 100:.1f}%" if stats_data.total_pets > 0 else "0%"],
        ["累计生成次数", stats_data.generation_count],
    ]
    click.echo(tabulate(overall_table, tablefmt="simple"))
    click.echo()
    
    if by_style and stats_data.style_distribution:
        click.echo(click.style("🎨 名字风格分布", fg="yellow"))
        style_table = _build_distribution_table(stats_data.style_distribution, STYLE_CN)
        click.echo(tabulate(style_table, headers=["风格", "数量", "占比"], tablefmt="simple"))
        click.echo()
    
    if by_language and stats_data.language_distribution:
        click.echo(click.style("🌍 语言分布", fg="yellow"))
        lang_table = _build_distribution_table(stats_data.language_distribution, LANGUAGE_CN)
        click.echo(tabulate(lang_table, headers=["语言", "数量", "占比"], tablefmt="simple"))
        click.echo()
    
    if by_species and stats_data.species_distribution:
        click.echo(click.style("🐾 物种分布", fg="yellow"))
        species_table = _build_distribution_table(stats_data.species_distribution, SPECIES_CN)
        click.echo(tabulate(species_table, headers=["物种", "数量", "占比"], tablefmt="simple"))
        click.echo()
    
    if by_batch and stats_data.batch_distribution:
        click.echo(click.style("📦 批次分布", fg="yellow"))
        batch_table = _build_distribution_table(stats_data.batch_distribution, {})
        click.echo(tabulate(batch_table, headers=["批次", "数量", "占比"], tablefmt="simple"))
        click.echo()
    
    if stats_data.top_names:
        click.echo(click.style(f"🏆 最热门名字 TOP {len(stats_data.top_names)}", fg="yellow"))
        top_table = []
        for i, (name, count, style, language) in enumerate(stats_data.top_names, 1):
            style_cn = STYLE_CN.get(style, style)
            lang_cn = LANGUAGE_CN.get(language, language)
            top_table.append([i, name, count, style_cn, lang_cn])
        click.echo(tabulate(top_table, headers=["排名", "名字", "使用次数", "风格", "语言"], tablefmt="simple"))
        click.echo()
    
    if records:
        _show_generation_records(storage)
    
    if output:
        import json
        from pathlib import Path
        output_path = Path(output)
        output_path.write_text(json.dumps(stats_data.to_dict(), ensure_ascii=False, indent=2))
        click.echo(click.style(f"\n已导出统计数据到 {output_path}", fg="green"))


def _compute_stats(storage, pets: List[Pet], name_library: List[NameEntry], top: int) -> StatsData:
    stats_data = StatsData()
    
    stats_data.total_pets = len(pets)
    stats_data.named_pets = sum(1 for p in pets if p.selected_name)
    
    name_counter = Counter()
    style_counter = Counter()
    language_counter = Counter()
    species_counter = Counter()
    batch_counter = Counter()
    
    name_info_map = {}
    for ne in name_library:
        name_info_map[ne.name.lower()] = ne
    
    for pet in pets:
        if pet.species:
            species_counter[pet.species] += 1
        
        if pet.batch:
            batch_counter[pet.batch] += 1
        
        if pet.selected_name:
            name_counter[pet.selected_name] += 1
            info = name_info_map.get(pet.selected_name.lower())
            if info:
                style_counter[info.style] += 1
                language_counter[info.language] += 1
        
        for name in pet.favorite_names:
            info = name_info_map.get(name.lower())
            if info:
                style_counter[info.style] += 1
                language_counter[info.language] += 1
    
    stats_data.style_distribution = dict(style_counter)
    stats_data.language_distribution = dict(language_counter)
    stats_data.species_distribution = dict(species_counter)
    stats_data.batch_distribution = dict(batch_counter)
    stats_data.generation_count = len(storage.load_records())
    
    top_names = []
    for name, count in name_counter.most_common(top):
        info = name_info_map.get(name.lower())
        style = info.style if info else "unknown"
        language = info.language if info else "unknown"
        top_names.append((name, count, style, language))
    stats_data.top_names = top_names
    
    return stats_data


def _build_distribution_table(distribution: Dict[str, int], name_map: Dict[str, str]) -> List[List]:
    total = sum(distribution.values())
    table = []
    for key, count in sorted(distribution.items(), key=lambda x: -x[1]):
        name = name_map.get(key, key)
        percentage = f"{count / total * 100:.1f}%" if total > 0 else "0%"
        bar = "█" * int(count / max(distribution.values()) * 20) if distribution else ""
        table.append([name, count, f"{percentage} {bar}"])
    return table


def _show_generation_records(storage):
    records = storage.load_records()
    
    if not records:
        click.echo("暂无生成记录")
        return
    
    click.echo(click.style("📜 生成记录历史", fg="yellow"))
    
    table_data = []
    for i, record in enumerate(reversed(records[-20:]), 1):
        timestamp = record.timestamp.split("T")[0] if "T" in record.timestamp else record.timestamp
        pet_count = len(record.pet_ids)
        style = record.params.style or "all"
        language = record.params.language or "all"
        batch = record.params.batch or "-"
        
        table_data.append([
            len(records) - i + 1,
            record.id[:8],
            timestamp,
            pet_count,
            STYLE_CN.get(style, style),
            LANGUAGE_CN.get(language, language),
            batch,
        ])
    
    click.echo(tabulate(
        table_data,
        headers=["#", "记录ID", "日期", "宠物数", "风格", "语言", "批次"],
        tablefmt="simple"
    ))
    click.echo()
    click.echo("使用 `pet-namer generate --replay <记录ID>` 复现某次生成参数")
