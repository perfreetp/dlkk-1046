import click
import json
import uuid
from pathlib import Path
from tabulate import tabulate
from typing import List

from ..models import Pet, GenerationParams, GenerationRecord
from ..generator import NameGenerator
from ..cli import pass_storage


@click.command()
@click.option("--species", type=click.Choice(["cat", "dog", "rabbit", "all"]), default="all", help="物种")
@click.option("--gender", type=click.Choice(["male", "female", "neutral"]), help="性别")
@click.option("--age", help="年龄 (如: 3m, 1y)")
@click.option("--coat-color", help="毛色")
@click.option("--personality", multiple=True, help="性格标签，可多次指定")
@click.option("--batch", help="来源批次")
@click.option("--min-length", type=int, help="名字最小长度")
@click.option("--max-length", type=int, help="名字最大长度")
@click.option("--language", type=click.Choice(["zh", "en", "all"]), default="all", help="语言风格")
@click.option("--style", type=click.Choice(["cute", "traditional", "western", "cool", "literary", "all"]), default="all", help="名字风格")
@click.option("--forbidden", multiple=True, help="禁用词，可多次指定")
@click.option("--count", type=int, default=5, help="每只宠物生成候选数")
@click.option("--exclude-used/--no-exclude-used", default=True, help="排除已使用的名字")
@click.option("--avoid-similar/--no-avoid-similar", default=True, help="避免发音相近的名字")
@click.option("--pet-id", multiple=True, help="指定宠物ID，可多次指定")
@click.option("--all", "all_pets", is_flag=True, help="为所有未命名宠物生成")
@click.option("--replay", help="从生成记录ID复现参数")
@click.option("--interactive/--no-interactive", default=True, help="交互式选择名字")
@click.option("--diff", "diff_ids", type=str, help="对比两条记录，格式: ID1:ID2")
@click.option("--diff-output", type=click.Path(), help="导出对比报告文件，后缀为 .txt 或 .json")
@click.option("--list-records/--no-list-records", default=False, help="列出所有生成记录")
@pass_storage
def generate(storage, species, gender, age, coat_color, personality, batch,
             min_length, max_length, language, style, forbidden, count,
             exclude_used, avoid_similar, pet_id, all_pets, replay, interactive,
             diff_ids, diff_output, list_records):
    """为宠物生成候选名字"""

    if list_records:
        _list_all_records(storage)
        return

    if diff_ids:
        _diff_records(storage, diff_ids, diff_output)
        return
    
    params = GenerationParams(
        species=None if species == "all" else species,
        gender=gender,
        age=age,
        coat_color=coat_color,
        personality=list(personality),
        batch=batch,
        min_length=min_length,
        max_length=max_length,
        language=None if language == "all" else language,
        style=None if style == "all" else style,
        forbidden_words=list(forbidden),
        candidates_per_pet=count,
        exclude_used=exclude_used,
        avoid_similar=avoid_similar,
    )

    if replay:
        record = storage.get_record(replay)
        if not record:
            raise click.ClickException(f"找不到生成记录: {replay}")
        params = record.params
        click.echo(f"已复现记录 {replay} 的生成参数")

    pets = _get_target_pets(storage, species, batch, pet_id, all_pets)
    if not pets:
        raise click.ClickException("没有找到符合条件的宠物")

    config = storage.load_config()
    if config.get("forbidden_words"):
        params.forbidden_words.extend(config["forbidden_words"])

    name_library = storage.load_names()
    generator = NameGenerator(name_library)

    used_names = storage.get_used_names() if exclude_used else []

    click.echo(f"\n正在为 {len(pets)} 只宠物生成候选名字...\n")

    results, record = generator.generate_batch(pets, params, used_names)

    for pet in pets:
        candidates = results.get(pet.id, [])
        if candidates:
            pet.candidate_names = candidates
            storage.update_pet(pet)

    storage.add_record(record)

    stats = storage.load_stats()
    stats.generation_count += 1
    storage.save_stats(stats)

    _display_results(storage, pets, results, generator, interactive)

    click.echo(f"\n生成记录ID: {record.id}")
    click.echo(f"可使用 `pet-namer generate --replay {record.id}` 复现本次参数")


def _get_target_pets(storage, species, batch, pet_ids, all_pets):
    pets = storage.load_pets()
    
    if pet_ids:
        target = [p for p in pets if p.id in pet_ids]
        if not target:
            raise click.ClickException("指定的宠物ID不存在")
        return target
    
    if all_pets:
        return [p for p in pets if not p.selected_name]
    
    filtered = []
    for p in pets:
        if p.selected_name:
            continue
        if species and species != "all" and p.species != species:
            continue
        if batch and p.batch != batch:
            continue
        filtered.append(p)
    
    if not filtered and pets:
        click.echo("所有宠物都已有名字，使用 --all 或 --pet-id 重新生成")
        return []
    
    return filtered


def _display_results(storage, pets, results, generator, interactive):
    for pet in pets:
        candidates = results.get(pet.id, [])
        
        pet_info = f"宠物 #{pet.id[:8]}"
        details = []
        if pet.species:
            details.append(pet.species)
        if pet.gender:
            details.append(pet.gender)
        if pet.coat_color:
            details.append(pet.coat_color)
        if pet.personality:
            details.append(",".join(pet.personality))
        
        click.echo(click.style(f"\n{pet_info} - {' '.join(details)}", fg="cyan", bold=True))
        
        if not candidates:
            click.echo("  没有找到合适的候选名字")
            continue
        
        table_data = []
        for i, name in enumerate(candidates, 1):
            info = generator.get_name_info(name)
            style = info.style if info else "-"
            lang = info.language if info else "-"
            meaning = info.meaning if info else "-"
            table_data.append([i, name, lang, style, meaning])
        
        click.echo(tabulate(table_data, headers=["#", "名字", "语言", "风格", "含义"], tablefmt="simple"))
        
        if interactive:
            choice = click.prompt(
                "\n选择一个名字作为正式名 (输入编号，0跳过，f收藏到候选，a全部收藏)",
                type=str,
                default="0"
            )
            
            if choice == "0":
                continue
            elif choice.lower() == "f":
                fav_num = click.prompt("输入要收藏的候选编号，多个用逗号分隔", type=str)
                try:
                    nums = [int(n.strip()) for n in fav_num.split(",")]
                    for n in nums:
                        if 1 <= n <= len(candidates):
                            fav_name = candidates[n - 1]
                            if fav_name not in pet.favorite_names:
                                pet.favorite_names.append(fav_name)
                    storage.update_pet(pet)
                    click.echo("已收藏到候选名单")
                except ValueError:
                    click.echo("输入无效，已跳过")
            elif choice.lower() == "a":
                for name in candidates:
                    if name not in pet.favorite_names:
                        pet.favorite_names.append(name)
                storage.update_pet(pet)
                click.echo("已将全部候选加入收藏")
            else:
                try:
                    idx = int(choice)
                    if 1 <= idx <= len(candidates):
                        selected = candidates[idx - 1]
                        pet.selected_name = selected
                        if selected not in pet.favorite_names:
                            pet.favorite_names.append(selected)
                        storage.update_pet(pet)
                        click.echo(click.style(f"已设置正式名: {selected}", fg="green"))
                except ValueError:
                    click.echo("输入无效，已跳过")


PARAM_LABELS = {
    "species": "物种",
    "gender": "性别",
    "age": "年龄",
    "age_min_months": "最小月龄",
    "age_max_months": "最大月龄",
    "coat_color": "毛色",
    "personality": "性格标签",
    "batch": "批次",
    "min_length": "名字最小长度",
    "max_length": "名字最大长度",
    "language": "语言",
    "style": "风格",
    "forbidden_words": "禁用词",
    "candidates_per_pet": "每只候选数",
    "exclude_used": "排除已用名",
    "avoid_similar": "避免发音相近",
}


def _list_all_records(storage):
    records = storage.load_records()
    if not records:
        click.echo("暂无生成记录")
        return
    
    click.echo(click.style("=== 生成记录列表 ===", fg="cyan", bold=True))
    
    table_data = []
    for i, record in enumerate(reversed(records), 1):
        ts = record.timestamp.split("T")[0] if "T" in record.timestamp else record.timestamp
        style = record.params.style or "all"
        language = record.params.language or "all"
        table_data.append([
            i,
            record.id[:8],
            ts,
            len(record.pet_ids),
            style,
            language,
            record.params.batch or "-",
        ])
    
    click.echo(tabulate(
        table_data,
        headers=["#", "记录ID", "日期", "宠物数", "风格", "语言", "批次"],
        tablefmt="simple"
    ))
    click.echo()
    click.echo("使用 `pet-namer generate --diff ID1:ID2` 对比两条记录")
    click.echo("使用 `pet-namer generate --replay <记录ID>` 复现某次生成")


def _diff_records(storage, diff_ids: str, output_path: str = None):
    if ":" not in diff_ids:
        raise click.ClickException("格式错误，请使用 ID1:ID2 格式")

    id_a, id_b = diff_ids.split(":", 1)

    record_a = storage.get_record(id_a)
    record_b = storage.get_record(id_b)

    if not record_a:
        raise click.ClickException(f"找不到记录: {id_a}")
    if not record_b:
        raise click.ClickException(f"找不到记录: {id_b}")

    ts_a = record_a.timestamp.replace("T", " ")
    ts_b = record_b.timestamp.replace("T", " ")
    info_data = {
        "record_a_id": record_a.id,
        "record_b_id": record_b.id,
        "record_a_timestamp": ts_a,
        "record_b_timestamp": ts_b,
        "record_a_pet_count": len(record_a.pet_ids),
        "record_b_pet_count": len(record_b.pet_ids),
    }

    param_a = record_a.params.to_dict()
    param_b = record_b.params.to_dict()
    all_keys = set(list(param_a.keys()) + list(param_b.keys()))
    param_diffs = []

    for key in sorted(all_keys):
        val_a = param_a.get(key)
        val_b = param_b.get(key)
        label = PARAM_LABELS.get(key, key)

        if val_a == val_b:
            continue

        def _fmt_val(v):
            if isinstance(v, list):
                return ", ".join(str(x) for x in v) or "(空)"
            if v is None:
                return "(未设置)"
            return str(v)

        param_diffs.append({
            "param": label,
            "param_key": key,
            "record_a": _fmt_val(val_a),
            "record_b": _fmt_val(val_b),
        })

    pets = storage.load_pets()
    pet_map = {p.id: p for p in pets}
    all_pet_ids = list(dict.fromkeys(record_a.pet_ids + record_b.pet_ids))
    pet_changes = []

    for pid in all_pet_ids:
        names_a = record_a.generated_names.get(pid, [])
        names_b = record_b.generated_names.get(pid, [])
        set_a = set(names_a)
        set_b = set(names_b)
        common = sorted(set_a & set_b)
        only_a = sorted(set_a - set_b)
        only_b = sorted(set_b - set_a)

        pet = pet_map.get(pid)
        pet_species = pet.species if pet else None
        pet_selected = pet.selected_name if pet else None

        pet_changes.append({
            "pet_id": pid,
            "pet_id_short": pid[:8],
            "species": pet_species,
            "selected_name": pet_selected,
            "names_a": names_a,
            "names_b": names_b,
            "common": common,
            "only_a": only_a,
            "only_b": only_b,
        })

    click.echo(click.style("=== 生成记录对比 ===", fg="cyan", bold=True))
    click.echo()

    click.echo(click.style("📋 基本信息", fg="yellow"))
    info_table = [
        ["", f"记录A ({id_a[:8]})", f"记录B ({id_b[:8]})"],
        ["生成时间", ts_a, ts_b],
        ["宠物数量", len(record_a.pet_ids), len(record_b.pet_ids)],
    ]
    click.echo(tabulate(info_table, tablefmt="simple", headers="firstrow"))
    click.echo()

    click.echo(click.style("⚙️ 参数差异", fg="yellow"))
    if param_diffs:
        rows = [[d["param"], d["record_a"], d["record_b"]] for d in param_diffs]
        click.echo(tabulate(rows, headers=["参数", "记录A", "记录B"], tablefmt="simple"))
    else:
        click.echo("  两条记录参数完全相同 ✅")
    click.echo()

    click.echo(click.style("🐾 宠物候选名变化", fg="yellow"))
    if pet_changes:
        rows = []
        for c in pet_changes:
            label = c["pet_id_short"]
            if c["species"]:
                label += f" ({c['species']})"
            if c["selected_name"]:
                label += f" [{c['selected_name']}]"
            rows.append([
                label,
                ", ".join(c["common"]) if c["common"] else "-",
                ", ".join(c["only_a"]) if c["only_a"] else "-",
                ", ".join(c["only_b"]) if c["only_b"] else "-",
            ])
        click.echo(tabulate(rows, headers=["宠物", "相同名字", "仅A有", "仅B有"], tablefmt="simple"))
    else:
        click.echo("  没有共同的宠物记录")
    click.echo()

    if output_path:
        _write_diff_report(output_path, info_data, param_diffs, pet_changes)
        click.echo(click.style(f"✅ 对比报告已导出到: {output_path}", fg="green"))


def _write_diff_report(output_path: str, info_data: dict, param_diffs: list, pet_changes: list):
    path = Path(output_path)
    suffix = path.suffix.lower()

    if suffix == ".json":
        report = {
            "report_type": "generation_diff",
            "basic_info": info_data,
            "param_diffs": param_diffs,
            "pet_changes": pet_changes,
        }
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        lines = []
        lines.append("=" * 60)
        lines.append("生成记录对比报告")
        lines.append("=" * 60)
        lines.append("")

        lines.append("【基本信息】")
        lines.append(f"记录A: {info_data['record_a_id']}  ({info_data['record_a_timestamp']})")
        lines.append(f"记录B: {info_data['record_b_id']}  ({info_data['record_b_timestamp']})")
        lines.append(f"宠物数量: A={info_data['record_a_pet_count']}, B={info_data['record_b_pet_count']}")
        lines.append("")

        lines.append("【参数差异】")
        if param_diffs:
            for d in param_diffs:
                lines.append(f"  * {d['param']}:")
                lines.append(f"      记录A: {d['record_a']}")
                lines.append(f"      记录B: {d['record_b']}")
        else:
            lines.append("  两条记录参数完全相同")
        lines.append("")

        lines.append("【宠物候选名变化】")
        for c in pet_changes:
            label = c["pet_id_short"]
            if c["species"]:
                label += f" ({c['species']})"
            if c["selected_name"]:
                label += f" 正式名:[{c['selected_name']}]"
            lines.append(f"  - {label}")
            if c["common"]:
                lines.append(f"      相同名字: {', '.join(c['common'])}")
            if c["only_a"]:
                lines.append(f"      仅A有:   {', '.join(c['only_a'])}")
            if c["only_b"]:
                lines.append(f"      仅B有:   {', '.join(c['only_b'])}")
            if not c["common"] and not c["only_a"] and not c["only_b"]:
                lines.append("      (无候选名)")
        lines.append("")

        path.write_text("\n".join(lines), encoding="utf-8")
