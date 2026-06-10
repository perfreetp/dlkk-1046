import click
import json
import uuid
from collections import defaultdict
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
@click.option("--diff", "diff_ids", type=str, help="对比两条记录，格式: ID1:ID2 (生成记录) 或 task:TASK1:TASK2 (批量任务)")
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
    if diff_ids.startswith("task:"):
        task_part = diff_ids[5:]
        if ":" not in task_part:
            raise click.ClickException("格式错误，任务对比请使用 task:TASK1:TASK2 格式")
        task_a_id, task_b_id = task_part.split(":", 1)
        _diff_tasks(storage, task_a_id, task_b_id, output_path)
        return

    if ":" not in diff_ids:
        raise click.ClickException("格式错误，请使用 ID1:ID2 或 task:TASK1:TASK2 格式")

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


TASK_STEP_LABELS = {
    "import": "导入宠物信息",
    "generate": "生成候选名字",
    "recommend": "自动挑选推荐名",
    "export": "导出领养名单",
}

TASK_PARAM_LABELS = {
    "import_file": "导入文件", "batch_name": "批次号",
    "count": "每只候选数", "style": "风格", "language": "语言",
    "species": "物种筛选", "recommend": "推荐策略",
    "auto_select": "自动设为正式名", "export_format": "导出格式",
    "owner": "负责人", "store": "门店", "tags": "标签",
    "handoff_status": "交接状态", "handoff_to": "交接给",
}


def _pet_signature(pet_dict):
    return (
        str(pet_dict.get("species", "") or "").lower(),
        str(pet_dict.get("gender", "") or "").lower(),
        str(pet_dict.get("coat_color", "") or "").lower(),
        str(pet_dict.get("batch", "") or "").lower(),
    )


def _build_sig_index(task_a, task_b, all_pets):
    pet_by_id = {p.id: p for p in all_pets}

    def _extract(task):
        items = []
        for r in task.reviews:
            p = pet_by_id.get(r.pet_id)
            item = {
                "pet_id": r.pet_id,
                "species": p.species if p else "",
                "gender": p.gender if p else "",
                "coat_color": p.coat_color if p else "",
                "batch": p.batch if p else "",
                "recommended_name": r.recommended_name,
                "final_name": r.final_name,
                "status": r.status,
            }
            items.append(item)
        return items

    a_items = _extract(task_a)
    b_items = _extract(task_b)

    exact = {}
    a_by_id = {x["pet_id"]: x for x in a_items}
    b_by_id = {x["pet_id"]: x for x in b_items}
    matched_a_ids = set()
    matched_b_ids = set()
    for pid in a_by_id:
        if pid in b_by_id:
            exact[pid] = (a_by_id[pid], b_by_id[pid])
            matched_a_ids.add(pid)
            matched_b_ids.add(pid)

    fuzzy = []
    remaining_a = [x for x in a_items if x["pet_id"] not in matched_a_ids]
    remaining_b = [x for x in b_items if x["pet_id"] not in matched_b_ids]

    a_sig = defaultdict(list)
    for x in remaining_a:
        sig = (x["species"], x["gender"], x["coat_color"], x["batch"])
        a_sig[sig].append(x)

    b_sig = defaultdict(list)
    for x in remaining_b:
        sig = (x["species"], x["gender"], x["coat_color"], x["batch"])
        b_sig[sig].append(x)

    for sig in set(a_sig.keys()) & set(b_sig.keys()):
        la = a_sig[sig]
        lb = b_sig[sig]
        n = min(len(la), len(lb))
        for i in range(n):
            fuzzy.append((la[i], lb[i]))
            matched_a_ids.add(la[i]["pet_id"])
            matched_b_ids.add(lb[i]["pet_id"])

    only_a = [x for x in a_items if x["pet_id"] not in matched_a_ids]
    only_b = [x for x in b_items if x["pet_id"] not in matched_b_ids]

    return exact, fuzzy, only_a, only_b


def _diff_tasks(storage, task_a_id, task_b_id, output_path=None):
    task_a = storage.get_task(task_a_id)
    task_b = storage.get_task(task_b_id)

    if not task_a:
        raise click.ClickException(f"找不到任务: {task_a_id}")
    if not task_b:
        raise click.ClickException(f"找不到任务: {task_b_id}")

    ts_a = task_a.timestamp.replace("T", " ").split(".")[0]
    ts_b = task_b.timestamp.replace("T", " ").split(".")[0]

    info_data = {
        "type": "task_diff",
        "task_a": {
            "id": task_a.id,
            "timestamp": ts_a,
            "owner": task_a.owner,
            "store": task_a.store,
            "tags": task_a.tags,
            "status": task_a.status,
            "handoff_status": task_a.handoff_status,
        },
        "task_b": {
            "id": task_b.id,
            "timestamp": ts_b,
            "owner": task_b.owner,
            "store": task_b.store,
            "tags": task_b.tags,
            "status": task_b.status,
            "handoff_status": task_b.handoff_status,
        },
    }

    step_names = ["import", "generate", "recommend", "export"]
    step_diffs = []
    for sname in step_names:
        step_a = next((s for s in task_a.steps if s.name == sname), None)
        step_b = next((s for s in task_b.steps if s.name == sname), None)
        sa_success = step_a.success_count if step_a else 0
        sa_total = step_a.total_count if step_a else 0
        sa_failed = step_a.failed_ids if step_a else []
        sb_success = step_b.success_count if step_b else 0
        sb_total = step_b.total_count if step_b else 0
        sb_failed = step_b.failed_ids if step_b else []
        diff = (sb_success - sa_success) if (step_a or step_b) else 0
        step_diffs.append({
            "step": sname,
            "step_label": TASK_STEP_LABELS.get(sname, sname),
            "task_a": f"{sa_success}/{sa_total}" + (f" ❌{len(sa_failed)}" if sa_failed else ""),
            "task_b": f"{sb_success}/{sb_total}" + (f" ❌{len(sb_failed)}" if sb_failed else ""),
            "task_a_success": sa_success,
            "task_a_total": sa_total,
            "task_a_failed_ids": sa_failed,
            "task_b_success": sb_success,
            "task_b_total": sb_total,
            "task_b_failed_ids": sb_failed,
            "diff": diff,
        })

    param_a = task_a.params
    param_b = task_b.params
    all_keys = set(list(param_a.keys()) + list(param_b.keys()))
    param_diffs = []

    def _fmt_val(v):
        if isinstance(v, list):
            return ", ".join(str(x) for x in v) or "(空)"
        if v is None:
            return "(未设置)"
        if isinstance(v, bool):
            return "是" if v else "否"
        return str(v)

    for key in sorted(all_keys):
        val_a = param_a.get(key)
        val_b = param_b.get(key)
        label = TASK_PARAM_LABELS.get(key, PARAM_LABELS.get(key, key))

        if val_a == val_b:
            continue

        param_diffs.append({
            "param": label,
            "param_key": key,
            "task_a": _fmt_val(val_a),
            "task_b": _fmt_val(val_b),
        })

    all_pets = storage.load_pets()
    exact, fuzzy, only_a, only_b = _build_sig_index(task_a, task_b, all_pets)

    export_diffs = {
        "export_file_a": task_a.export_file,
        "export_file_b": task_b.export_file,
        "gen_record_a": task_a.generation_record_id,
        "gen_record_b": task_b.generation_record_id,
    }

    a_total = len(task_a.reviews)
    b_total = len(task_b.reviews)
    delta = b_total - a_total
    n_add = len(only_b)
    n_del = len(only_a)
    x_count = len(exact)
    y_count = len(fuzzy)

    matched_pairs = list(exact.values()) + fuzzy
    n_final_changed = 0
    n1 = 0
    n2 = 0
    n3 = 0
    n4 = 0
    for item_a, item_b in matched_pairs:
        fa = item_a.get("final_name")
        fb = item_b.get("final_name")
        if fa != fb:
            n_final_changed += 1
            if fa and fb:
                rec_a = item_a.get("recommended_name")
                if fa == rec_a and fb != rec_a and fb != item_b.get("recommended_name"):
                    n1 += 1
                else:
                    n2 += 1
            elif fa and not fb:
                n3 += 1
            elif not fa and fb:
                n4 += 1

    top_params = []
    for d in param_diffs[:3]:
        top_params.append(f"{d['param']}: {d['task_a']} → {d['task_b']}")

    summary = {
        "total_a": a_total,
        "total_b": b_total,
        "delta": delta,
        "n_add": n_add,
        "n_del": n_del,
        "exact_count": x_count,
        "fuzzy_count": y_count,
        "final_name_changed": n_final_changed,
        "final_name_change_types": {
            "recommend_to_custom": n1,
            "custom_to_another": n2,
            "has_to_none": n3,
            "none_to_has": n4,
        },
        "export_file_a": export_diffs["export_file_a"],
        "export_file_b": export_diffs["export_file_b"],
        "status_a": task_a.status,
        "status_b": task_b.status,
        "top_param_diffs": top_params,
    }

    click.echo(click.style("=== 批量任务对比 ===", fg="cyan", bold=True))
    click.echo()

    click.echo(click.style("📋 基本信息", fg="yellow"))
    info_table = [
        ["", f"任务A ({task_a.id[:8]})", f"任务B ({task_b.id[:8]})"],
        ["任务ID", task_a.id, task_b.id],
        ["创建时间", ts_a, ts_b],
        ["负责人", task_a.owner or "-", task_b.owner or "-"],
        ["门店", task_a.store or "-", task_b.store or "-"],
        ["标签", ",".join(task_a.tags) if task_a.tags else "-", ",".join(task_b.tags) if task_b.tags else "-"],
        ["状态", task_a.status, task_b.status],
        ["交接状态", task_a.handoff_status or "-", task_b.handoff_status or "-"],
    ]
    click.echo(tabulate(info_table, tablefmt="simple", headers="firstrow"))
    click.echo()

    click.echo(click.style("📊 步骤数量对比", fg="yellow"))
    step_rows = []
    for sd in step_diffs:
        diff_str = f"+{sd['diff']}" if sd['diff'] > 0 else str(sd['diff']) if sd['diff'] < 0 else "0"
        step_rows.append([sd["step_label"], sd["task_a"], sd["task_b"], diff_str])
    click.echo(tabulate(step_rows, headers=["步骤", "任务A", "任务B", "差异"], tablefmt="simple"))
    click.echo()

    click.echo(click.style("⚙️ 参数差异", fg="yellow"))
    if param_diffs:
        rows = [[d["param"], d["task_a"], d["task_b"]] for d in param_diffs]
        click.echo(tabulate(rows, headers=["参数", "任务A", "任务B"], tablefmt="simple"))
    else:
        click.echo("  两个任务参数完全相同 ✅")
    click.echo()

    click.echo(click.style("� 宠物匹配总结", fg="yellow"))
    summary_rows = [
        ["完全匹配(ID)", x_count],
        ["模糊匹配(属性)", y_count],
        ["仅在任务A", len(only_a)],
        ["仅在任务B", len(only_b)],
    ]
    click.echo(tabulate(summary_rows, headers=["类型", "数量"], tablefmt="simple"))
    click.echo()

    def _build_match_rows(pairs, mark_fuzzy=False):
        rows = []
        for item_a, item_b in pairs:
            pid_display = item_a["pet_id"][:8]
            if mark_fuzzy:
                pid_display += "*"
            status_change = f"{item_a.get('status') or '-'} → {item_b.get('status') or '-'}"
            rows.append([
                pid_display,
                item_a.get("recommended_name") or "-",
                item_b.get("recommended_name") or "-",
                item_a.get("final_name") or "-",
                item_b.get("final_name") or "-",
                status_change,
            ])
        return rows

    headers = ["pet_id", "任务A推荐名", "任务B推荐名", "任务A最终名", "任务B最终名", "状态变化"]

    click.echo(click.style("🐾 完全匹配的宠物（ID相同）", fg="yellow"))
    exact_rows = _build_match_rows(list(exact.values()), mark_fuzzy=False)
    if exact_rows:
        click.echo(tabulate(exact_rows, headers=headers, tablefmt="simple"))
    else:
        click.echo("  (无)")
    click.echo()

    click.echo(click.style("🐾 模糊匹配的宠物（属性相同）", fg="yellow"))
    fuzzy_rows = _build_match_rows(fuzzy, mark_fuzzy=True)
    if fuzzy_rows:
        click.echo(tabulate(fuzzy_rows, headers=headers, tablefmt="simple"))
        click.echo("  * 注: pet_id 带 * 标记表示按 (物种,性别,毛色,批次) 属性进行的模糊匹配")
    else:
        click.echo("  (无)")
    click.echo()

    def _build_only_rows(items):
        rows = []
        for it in items:
            rows.append([
                it["pet_id"][:8],
                it.get("species") or "-",
                it.get("gender") or "-",
                it.get("coat_color") or "-",
                it.get("batch") or "-",
                it.get("recommended_name") or "-",
                it.get("final_name") or "-",
                it.get("status") or "-",
            ])
        return rows

    only_headers = ["pet_id", "物种", "性别", "毛色", "批次", "推荐名", "最终名", "状态"]

    click.echo(click.style("❌ 仅在任务A中的宠物", fg="yellow"))
    only_a_rows = _build_only_rows(only_a)
    if only_a_rows:
        click.echo(tabulate(only_a_rows, headers=only_headers, tablefmt="simple"))
    else:
        click.echo("  (无)")
    click.echo()

    click.echo(click.style("✅ 仅在任务B中的宠物", fg="yellow"))
    only_b_rows = _build_only_rows(only_b)
    if only_b_rows:
        click.echo(tabulate(only_b_rows, headers=only_headers, tablefmt="simple"))
    else:
        click.echo("  (无)")
    click.echo()

    click.echo(click.style("📤 导出文件对比", fg="yellow"))
    export_rows = [
        ["导出文件", export_diffs["export_file_a"] or "-", export_diffs["export_file_b"] or "-"],
        ["生成记录ID", export_diffs["gen_record_a"] or "-", export_diffs["gen_record_b"] or "-"],
    ]
    click.echo(tabulate(export_rows, headers=["", "任务A", "任务B"], tablefmt="simple"))
    click.echo()

    delta_sign = "+" if delta > 0 else ""
    click.echo(click.style("🔔 活动复盘摘要", fg="yellow"))
    click.echo("-" * 50)
    click.echo(f"  总宠物变化：A={a_total} 只 -> B={b_total} 只（净变化: {delta_sign}{delta}）")
    click.echo(f"  新增宠物（B比A多）：{n_add} 只")
    click.echo(f"  减少宠物（A比B多）：{n_del} 只")
    click.echo(f"  宠物匹配：{x_count} 只ID完全相同，{y_count} 只属性相似")
    click.echo(f"  正式名变化：{n_final_changed} 只匹配宠物的正式名发生了改变")
    if n_final_changed > 0:
        click.echo(f"    - 其中：接受推荐 -> 自定义名：{n1}")
        click.echo(f"            自定义 -> 另一自定义：{n2}")
        click.echo(f"            有正式名 -> 无正式名：{n3}")
        click.echo(f"            无 -> 有：{n4}")
    click.echo(f"  导出文件变化：")
    click.echo(f"    A: {export_diffs['export_file_a'] or '(未导出)'}")
    click.echo(f"    B: {export_diffs['export_file_b'] or '(未导出)'}")
    click.echo(f"  审核状态变化：A:{task_a.status} -> B:{task_b.status}")
    if top_params:
        click.echo(f"  策略变化：")
        for tp in top_params:
            click.echo(f"    - {tp}")
    else:
        click.echo(f"  策略变化：参数无显著差异")
    click.echo("-" * 50)
    click.echo()

    if output_path:
        _write_task_diff_report(
            output_path, info_data, step_diffs, param_diffs,
            exact, fuzzy, only_a, only_b, export_diffs, summary
        )
        click.echo(click.style(f"✅ 对比报告已导出到: {output_path}", fg="green"))


def _write_task_diff_report(output_path: str, info_data: dict, step_diffs: list,
                            param_diffs: list, exact: dict, fuzzy: list,
                            only_a: list, only_b: list, export_diffs: dict,
                            summary: dict):
    path = Path(output_path)
    suffix = path.suffix.lower()
    task_a = info_data["task_a"]
    task_b = info_data["task_b"]

    def _format_pair_list(pairs, mark_fuzzy=False):
        result = []
        for item_a, item_b in pairs:
            pid = item_a["pet_id"]
            if mark_fuzzy:
                pid = pid + "*"
            result.append({
                "pet_id": pid,
                "pet_id_short": pid[:8],
                "pet_a": item_a,
                "pet_b": item_b,
            })
        return result

    exact_matches_list = [
        {
            "pet_id": pid,
            "pet_id_short": pid[:8],
            "pet_a": item_a,
            "pet_b": item_b,
        }
        for pid, (item_a, item_b) in exact.items()
    ]
    fuzzy_matches_list = _format_pair_list(fuzzy, mark_fuzzy=True)

    if suffix == ".json":
        report = {
            "report_type": "task_diff",
            "basic_info": info_data,
            "step_diffs": step_diffs,
            "param_diffs": param_diffs,
            "exact_matches": exact_matches_list,
            "fuzzy_matches": fuzzy_matches_list,
            "only_in_a": only_a,
            "only_in_b": only_b,
            "export_diffs": export_diffs,
            "summary": summary,
        }
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        lines = []
        lines.append("=" * 60)
        lines.append("批量任务对比报告")
        lines.append("=" * 60)
        lines.append("")

        lines.append("【基本信息】")
        lines.append(f"任务A: {task_a['id']}  ({task_a['timestamp']})")
        lines.append(f"任务B: {task_b['id']}  ({task_b['timestamp']})")
        lines.append(f"负责人: A={task_a['owner'] or '-'}, B={task_b['owner'] or '-'}")
        lines.append(f"门店:   A={task_a['store'] or '-'}, B={task_b['store'] or '-'}")
        lines.append(f"标签:   A={','.join(task_a['tags']) if task_a['tags'] else '-'}, B={','.join(task_b['tags']) if task_b['tags'] else '-'}")
        lines.append(f"状态:   A={task_a['status']}, B={task_b['status']}")
        lines.append(f"交接状态: A={task_a['handoff_status'] or '-'}, B={task_b['handoff_status'] or '-'}")
        lines.append("")

        lines.append("【步骤数量对比】")
        for sd in step_diffs:
            diff_str = f"+{sd['diff']}" if sd['diff'] > 0 else str(sd['diff']) if sd['diff'] < 0 else "0"
            lines.append(f"  * {sd['step_label']}: A={sd['task_a']}, B={sd['task_b']}, 差异={diff_str}")
            if sd["task_a_failed_ids"]:
                lines.append(f"      A失败ID: {', '.join(sd['task_a_failed_ids'])}")
            if sd["task_b_failed_ids"]:
                lines.append(f"      B失败ID: {', '.join(sd['task_b_failed_ids'])}")
        lines.append("")

        lines.append("【参数差异】")
        if param_diffs:
            for d in param_diffs:
                lines.append(f"  * {d['param']}:")
                lines.append(f"      任务A: {d['task_a']}")
                lines.append(f"      任务B: {d['task_b']}")
        else:
            lines.append("  两个任务参数完全相同")
        lines.append("")

        lines.append("【宠物匹配总结】")
        lines.append(f"  完全匹配(ID):  {summary['exact_count']}")
        lines.append(f"  模糊匹配(属性): {summary['fuzzy_count']}")
        lines.append(f"  仅在任务A:     {len(only_a)}")
        lines.append(f"  仅在任务B:     {len(only_b)}")
        lines.append("")

        lines.append("【完全匹配的宠物（ID相同）】")
        if exact_matches_list:
            for m in exact_matches_list:
                ia, ib = m["pet_a"], m["pet_b"]
                lines.append(f"  - {m['pet_id_short']}:")
                lines.append(f"      推荐名: {ia.get('recommended_name') or '-'} → {ib.get('recommended_name') or '-'}")
                lines.append(f"      最终名: {ia.get('final_name') or '-'} → {ib.get('final_name') or '-'}")
                lines.append(f"      状态:   {ia.get('status') or '-'} → {ib.get('status') or '-'}")
        else:
            lines.append("  (无)")
        lines.append("")

        lines.append("【模糊匹配的宠物（属性相同）】")
        if fuzzy_matches_list:
            for m in fuzzy_matches_list:
                ia, ib = m["pet_a"], m["pet_b"]
                lines.append(f"  - {m['pet_id_short']}* (A={ia['pet_id'][:8]} ↔ B={ib['pet_id'][:8]}):")
                lines.append(f"      推荐名: {ia.get('recommended_name') or '-'} → {ib.get('recommended_name') or '-'}")
                lines.append(f"      最终名: {ia.get('final_name') or '-'} → {ib.get('final_name') or '-'}")
                lines.append(f"      状态:   {ia.get('status') or '-'} → {ib.get('status') or '-'}")
            lines.append("  * 注: 带 * 标记表示按 (物种,性别,毛色,批次) 属性进行的模糊匹配")
        else:
            lines.append("  (无)")
        lines.append("")

        lines.append("【仅在任务A中的宠物】")
        if only_a:
            for it in only_a:
                lines.append(f"  - {it['pet_id'][:8]}: 物种={it.get('species') or '-'}, 性别={it.get('gender') or '-'}, "
                             f"毛色={it.get('coat_color') or '-'}, 批次={it.get('batch') or '-'}, "
                             f"推荐名={it.get('recommended_name') or '-'}, 最终名={it.get('final_name') or '-'}, "
                             f"状态={it.get('status') or '-'}")
        else:
            lines.append("  (无)")
        lines.append("")

        lines.append("【仅在任务B中的宠物】")
        if only_b:
            for it in only_b:
                lines.append(f"  - {it['pet_id'][:8]}: 物种={it.get('species') or '-'}, 性别={it.get('gender') or '-'}, "
                             f"毛色={it.get('coat_color') or '-'}, 批次={it.get('batch') or '-'}, "
                             f"推荐名={it.get('recommended_name') or '-'}, 最终名={it.get('final_name') or '-'}, "
                             f"状态={it.get('status') or '-'}")
        else:
            lines.append("  (无)")
        lines.append("")

        lines.append("【导出文件对比】")
        lines.append(f"  导出文件:   A={export_diffs['export_file_a'] or '-'}, B={export_diffs['export_file_b'] or '-'}")
        lines.append(f"  生成记录ID: A={export_diffs['gen_record_a'] or '-'}, B={export_diffs['gen_record_b'] or '-'}")
        lines.append("")

        lines.append("【活动复盘摘要】")
        lines.append("-" * 50)
        delta_sign = "+" if summary["delta"] > 0 else ""
        lines.append(f"  总宠物变化：A={summary['total_a']} 只 -> B={summary['total_b']} 只（净变化: {delta_sign}{summary['delta']}）")
        lines.append(f"  新增宠物（B比A多）：{summary['n_add']} 只")
        lines.append(f"  减少宠物（A比B多）：{summary['n_del']} 只")
        lines.append(f"  宠物匹配：{summary['exact_count']} 只ID完全相同，{summary['fuzzy_count']} 只属性相似")
        lines.append(f"  正式名变化：{summary['final_name_changed']} 只匹配宠物的正式名发生了改变")
        if summary["final_name_changed"] > 0:
            ftypes = summary["final_name_change_types"]
            lines.append(f"    - 其中：接受推荐 -> 自定义名：{ftypes['recommend_to_custom']}")
            lines.append(f"            自定义 -> 另一自定义：{ftypes['custom_to_another']}")
            lines.append(f"            有正式名 -> 无正式名：{ftypes['has_to_none']}")
            lines.append(f"            无 -> 有：{ftypes['none_to_has']}")
        lines.append(f"  导出文件变化：")
        lines.append(f"    A: {summary['export_file_a'] or '(未导出)'}")
        lines.append(f"    B: {summary['export_file_b'] or '(未导出)'}")
        lines.append(f"  审核状态变化：A:{summary['status_a']} -> B:{summary['status_b']}")
        if summary["top_param_diffs"]:
            lines.append(f"  策略变化：")
            for tp in summary["top_param_diffs"]:
                lines.append(f"    - {tp}")
        else:
            lines.append(f"  策略变化：参数无显著差异")
        lines.append("-" * 50)
        lines.append("")

        path.write_text("\n".join(lines), encoding="utf-8")
