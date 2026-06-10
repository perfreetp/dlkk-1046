import click
import json
import csv
from pathlib import Path
from tabulate import tabulate
from typing import List, Dict, Optional
from datetime import datetime

from ..models import Pet, ReviewEntry, BatchTaskRecord
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
@click.option("--group-by-species/--no-group-by-species", default=False, help="按物种分组输出")
@click.option("--contact-phone", help="联系电话（模板字段）")
@click.option("--location", help="领养地点（模板字段）")
@click.option("--event-date", help="活动日期（模板字段，如 2024-07-01）")
@click.option("--event-name", help="活动名称（模板字段）")
@click.option("--organizer", help="主办方/救助站名称（模板字段）")
@click.option("--note", "event_note", help="活动说明/备注（模板字段）")
@click.option("--qr-code", help="二维码/报名链接（模板字段）")
@click.option("--custom-field", "custom_fields", multiple=True,
              help="自定义模板字段 key=value，可多次指定，如 wechat=adopt2024")
@click.option("--template", help="模板配置文件路径（YAML/JSON），可一次设置所有模板字段")
@click.option("--preview", type=int, default=0, help="导出前预览前N行内容")
@click.option("--task-id", help="关联的批量任务ID，用于生成交接摘要信息")
@click.option("--owner", help="负责人姓名")
@click.option("--store", help="门店名称")
@pass_storage
def export(storage, fmt, output, pet_ids, batch, species, named_only,
           include_candidates, include_favorites, group_by_species,
           contact_phone, location, event_date, event_name, organizer, event_note,
           qr_code, custom_fields, template, preview, task_id, owner, store):
    """导出领养海报名单或数据文件"""

    template_data = _load_template(template)
    for key, val in [
        ("contact_phone", contact_phone),
        ("location", location),
        ("event_date", event_date),
        ("event_name", event_name),
        ("organizer", organizer),
        ("note", event_note),
        ("qr_code", qr_code),
    ]:
        if val:
            template_data[key] = val

    if custom_fields:
        for cf in custom_fields:
            if "=" in cf:
                k, v = cf.split("=", 1)
                template_data[k.strip()] = v.strip()
            else:
                template_data[cf] = ""

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

    task_obj = storage.get_task(task_id) if task_id else None
    handover_summary = _build_handover_summary(
        pets,
        reviews=task_obj.reviews if task_obj else None,
        task=task_obj,
        owner=owner,
        store=store,
    )

    if fmt == "poster":
        content = _generate_poster(pets, include_candidates, include_favorites, group_by_species, template_data, handover_summary)
    elif fmt == "csv":
        content = _generate_csv(pets, include_candidates, include_favorites, template_data, group_by_species, handover_summary)
    elif fmt == "json":
        content = _generate_json(pets, include_candidates, include_favorites, template_data, group_by_species, handover_summary)
    elif fmt == "excel":
        if not output:
            output = "adoption_list.xlsx"
        _generate_excel(storage, pets, output, include_candidates, include_favorites, template_data, group_by_species, handover_summary)
        click.echo(click.style(f"\n已导出到 {output}", fg="green"))
        return

    if preview and preview > 0:
        lines = content.splitlines()
        preview_lines = lines[:preview]
        click.echo(click.style(f"=== 预览前 {len(preview_lines)} 行 ===", fg="cyan"))
        for pl in preview_lines:
            click.echo(pl)
        click.echo(click.style("=== 预览结束 ===", fg="cyan"))
        click.echo()
        if not click.confirm("是否继续导出？", default=True):
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


def _load_template(template_path: str = None) -> dict:
    if not template_path:
        return {}
    
    path = Path(template_path)
    if not path.exists():
        raise click.ClickException(f"模板文件不存在: {template_path}")
    
    text = path.read_text(encoding="utf-8")
    
    if template_path.endswith((".yaml", ".yml")):
        try:
            import yaml
            return yaml.safe_load(text) or {}
        except ImportError:
            raise click.ClickException("需要安装 PyYAML 以支持 YAML 模板: pip install pyyaml")
    elif template_path.endswith(".json"):
        return json.loads(text)
    else:
        raise click.ClickException("仅支持 YAML 和 JSON 格式的模板文件")


def _build_handover_summary(pets: List[Pet], reviews: Optional[List[ReviewEntry]] = None,
                            task: Optional[BatchTaskRecord] = None,
                            owner: Optional[str] = None, store: Optional[str] = None) -> dict:
    species_breakdown: Dict[str, Dict[str, int]] = {}
    for sp_key in ["cat", "dog", "rabbit"]:
        sp_pets = [p for p in pets if p.species == sp_key]
        sp_named = sum(1 for p in sp_pets if p.selected_name)
        species_breakdown[sp_key] = {
            "count": len(sp_pets),
            "named_count": sp_named,
            "missing_count": len(sp_pets) - sp_named,
        }

    named_count = sum(1 for p in pets if p.selected_name)
    total_count = len(pets)

    summary = {
        "generated_at": datetime.now().isoformat(),
        "owner": owner or (task.owner if task else None),
        "store": store or (task.store if task else None),
        "total_count": total_count,
        "species_breakdown": species_breakdown,
        "named_count": named_count,
        "missing_count": total_count - named_count,
        "task_id": task.id if task else None,
        "task_status": task.status if task else None,
    }

    if reviews:
        review_stats = {
            "accepted": 0,
            "modified": 0,
            "rejected": 0,
            "pending": 0,
        }
        for r in reviews:
            if r.status in review_stats:
                review_stats[r.status] += 1
        summary["review_stats"] = review_stats

    return summary


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


STANDARD_TEMPLATE_LABELS = {
    "event_name": "活动名称",
    "event_date": "活动日期",
    "location": "领养地点",
    "contact_phone": "联系电话",
    "organizer": "主办方",
    "note": "活动说明",
    "qr_code": "报名链接",
}


def _build_event_header(template_data: dict, width: int = 60) -> List[str]:
    lines = []
    event_name = template_data.get("event_name", "")
    event_date = template_data.get("event_date", "")
    location = template_data.get("location", "")
    contact_phone = template_data.get("contact_phone", "")
    organizer = template_data.get("organizer", "")

    title = f"🐾 {event_name or '待领养宠物名单'} 🐾"
    lines.append("=" * width)
    lines.append(f"{title:^{width}}")

    top_parts = []
    if organizer:
        top_parts.append(f"🤝 {organizer}")
    if event_date:
        top_parts.append(f"📅 {event_date}")
    if top_parts:
        lines.append(f"{'  |  '.join(top_parts):^{width}}")

    mid_parts = []
    if location:
        mid_parts.append(f"📍 {location}")
    if contact_phone:
        mid_parts.append(f"📞 {contact_phone}")
    if mid_parts:
        lines.append(f"{'  |  '.join(mid_parts):^{width}}")

    lines.append("=" * width)
    lines.append("")
    return lines


def _build_event_footer(template_data: dict, total_count: int, width: int = 60) -> List[str]:
    lines = []
    lines.append("=" * width)
    lines.append(f"共 {total_count} 只萌宠等待温暖的家")

    contact_phone = template_data.get("contact_phone", "")
    location = template_data.get("location", "")
    if contact_phone or location:
        contact_line = "📞 "
        if contact_phone:
            contact_line += contact_phone
        if location:
            contact_line += f"  |  📍 {location}"
        lines.append(contact_line)

    for key in ["organizer", "note", "qr_code"]:
        val = template_data.get(key)
        if val:
            label = STANDARD_TEMPLATE_LABELS.get(key, key)
            icon = {"organizer": "🤝", "note": "📝", "qr_code": "🔗"}.get(key, "•")
            lines.append(f"{icon} {label}: {val}")

    custom_labeled_keys = set(list(STANDARD_TEMPLATE_LABELS.keys()) + ["event_name", "event_date", "location", "contact_phone"])
    for key, val in template_data.items():
        if key not in custom_labeled_keys and val:
            label = key
            lines.append(f"• {label}: {val}")

    lines.append("💕 领养代替购买，用爱温暖生命 💕")
    lines.append("=" * width)
    return lines


def _generate_poster(pets: List[Pet], include_candidates: bool, include_favorites: bool,
                     group_by_species: bool, template_data: dict,
                     handover_summary: Optional[dict] = None) -> str:
    lines = []
    width = 60

    if handover_summary:
        hs = handover_summary
        lines.append("=" * width)
        lines.append(f"{'========== 活动交接摘要 ==========':^{width}}")
        lines.append(f"📅 生成时间: {hs.get('generated_at', '')}")
        owner_val = hs.get("owner") or "-"
        store_val = hs.get("store") or "-"
        lines.append(f"👤 负责人: {owner_val}      🏪 门店: {store_val}")
        task_id_val = hs.get("task_id") or "-"
        task_status_val = hs.get("task_status") or "-"
        lines.append(f"📋 任务ID: {task_id_val}      📊 任务状态: {task_status_val}")
        total = hs.get("total_count", 0)
        named = hs.get("named_count", 0)
        missing = hs.get("missing_count", 0)
        lines.append(f"🐾 总计 {total} 只：已起名 {named} 只，未起名 {missing} 只")
        species_breakdown = hs.get("species_breakdown", {})
        for sp_key, sp_label in [("cat", "猫咪"), ("dog", "狗狗"), ("rabbit", "兔子")]:
            sp_info = species_breakdown.get(sp_key, {"count": 0, "named_count": 0, "missing_count": 0})
            lines.append(f"  {sp_label} {sp_info['count']} 只（已起名 {sp_info['named_count']}，缺 {sp_info['missing_count']}）")
        review_stats = hs.get("review_stats")
        if review_stats:
            lines.append(
                f"✅ 审核：已接受 {review_stats.get('accepted', 0)} / "
                f"已修改 {review_stats.get('modified', 0)} / "
                f"已拒绝 {review_stats.get('rejected', 0)} / "
                f"待审核 {review_stats.get('pending', 0)}"
            )
        lines.append("=" * width)
        lines.append("")

    lines.extend(_build_event_header(template_data, width))
    
    contact_phone = template_data.get("contact_phone", "")
    contact_msg = f"请联系 {contact_phone}" if contact_phone else "请联系救助站"
    
    if group_by_species:
        species_groups: Dict[str, List[Pet]] = {}
        for pet in pets:
            key = pet.species or "unknown"
            if key not in species_groups:
                species_groups[key] = []
            species_groups[key].append(pet)
        
        order = ["cat", "dog", "rabbit"]
        ordered_keys = [k for k in order if k in species_groups] + [k for k in species_groups if k not in order]
        
        for sp_key in ordered_keys:
            sp_pets = species_groups[sp_key]
            sp_name = SPECIES_CN.get(sp_key, sp_key)
            emoji = "🐱" if sp_key == "cat" else "🐶" if sp_key == "dog" else "🐰"
            lines.append(f"{emoji}=== {sp_name}组 ({len(sp_pets)}只) ===")
            lines.append("")
            
            for i, pet in enumerate(sp_pets, 1):
                lines.append(f"【{sp_name}{i:02d}号】")
                lines.append("-" * 40)
                lines.append(_generate_single_poster(pet, include_candidates, include_favorites, contact_msg))
                lines.append("")
    else:
        if len(pets) == 1:
            lines.append(_generate_single_poster(pets[0], include_candidates, include_favorites, contact_msg))
        else:
            for i, pet in enumerate(pets, 1):
                lines.append(f"【第 {i} 号】")
                lines.append("-" * 40)
                lines.append(_generate_single_poster(pet, include_candidates, include_favorites, contact_msg))
                lines.append("")
    
    lines.extend(_build_event_footer(template_data, len(pets), width))
    return "\n".join(lines)


def _is_valid_note(val) -> bool:
    if not val:
        return False
    s = str(val).strip()
    if not s:
        return False
    if s.lower() in ["nan", "none", "null", "-", "无", "空", "n/a", "na"]:
        return False
    return True


def _generate_single_poster(pet: Pet, include_candidates: bool, include_favorites: bool,
                            contact_msg: str = "请联系救助站") -> str:
    lines = []
    
    species = SPECIES_CN.get(pet.species, pet.species)
    gender = GENDER_CN.get(pet.gender, pet.gender or "未知")
    age = pet.age or "年龄不详"
    color = pet.coat_color or "毛色不详"
    personality = ", ".join(pet.personality) if pet.personality else "性格温顺"
    
    emoji = "🐱" if pet.species == "cat" else "🐶" if pet.species == "dog" else "🐰"
    
    if pet.selected_name:
        lines.append(f"{emoji} 名字: {pet.selected_name}")
    else:
        lines.append(f"{emoji} 名字: (待命名)")
    
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
    
    if _is_valid_note(pet.notes):
        lines.append(f"   备注: {pet.notes}")
    
    lines.append("")
    lines.append(f"   💕 如果您对我感兴趣，{contact_msg} 💕")
    
    return "\n".join(lines)


def _build_pet_row(pet: Pet, include_candidates: bool, include_favorites: bool,
                   add_group: bool = False):
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
    row.append(pet.notes if _is_valid_note(pet.notes) else "")
    if add_group:
        row.insert(0, SPECIES_CN.get(pet.species, pet.species or "其他"))
    return row


def _build_pet_dict(pet: Pet, include_candidates: bool, include_favorites: bool):
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
        "notes": pet.notes if _is_valid_note(pet.notes) else "",
        "created_at": pet.created_at,
    }
    if include_favorites:
        item["favorite_names"] = pet.favorite_names
    if include_candidates:
        item["candidate_names"] = pet.candidate_names
    return item


def _generate_csv(pets: List[Pet], include_candidates: bool, include_favorites: bool,
                  template_data: dict, group_by_species: bool = False,
                  handover_summary: Optional[dict] = None) -> str:
    import io

    output = io.StringIO()
    writer = csv.writer(output)

    if handover_summary:
        hs = handover_summary
        writer.writerow(["# 交接摘要"])
        writer.writerow([f"# 生成时间: {hs.get('generated_at', '')}"])
        writer.writerow([f"# 负责人: {hs.get('owner') or '-'}"])
        writer.writerow([f"# 门店: {hs.get('store') or '-'}"])
        writer.writerow([f"# 任务ID: {hs.get('task_id') or '-'}"])
        writer.writerow([
            f"# 总览: 总计{hs.get('total_count', 0)}只 / "
            f"已起名{hs.get('named_count', 0)} / "
            f"缺{hs.get('missing_count', 0)}"
        ])
        species_breakdown = hs.get("species_breakdown", {})
        species_parts = []
        for sp_key, sp_label in [("cat", "猫咪"), ("dog", "狗狗"), ("rabbit", "兔子")]:
            sp_info = species_breakdown.get(sp_key, {"count": 0, "named_count": 0, "missing_count": 0})
            species_parts.append(
                f"{sp_label} {sp_info['count']}(已{sp_info['named_count']}/缺{sp_info['missing_count']})"
            )
        writer.writerow([f"# 物种: {' | '.join(species_parts)}"])
        review_stats = hs.get("review_stats")
        if review_stats:
            writer.writerow([
                f"# 审核: 已接受{review_stats.get('accepted', 0)} / "
                f"已修改{review_stats.get('modified', 0)} / "
                f"已拒绝{review_stats.get('rejected', 0)} / "
                f"待审核{review_stats.get('pending', 0)}"
            ])
        writer.writerow([])

    if template_data:
        writer.writerow(["活动信息"])
        all_keys = list(STANDARD_TEMPLATE_LABELS.keys()) + [
            k for k in template_data.keys() if k not in STANDARD_TEMPLATE_LABELS
        ]
        for key in all_keys:
            val = template_data.get(key, "")
            if val:
                cn_key = STANDARD_TEMPLATE_LABELS.get(key, key)
                writer.writerow([cn_key, val])
        writer.writerow([])

    headers = []
    if group_by_species:
        headers.append("物种组")
    headers.extend(["ID", "物种", "性别", "年龄", "月龄", "毛色", "性格", "批次", "来源", "正式名"])
    if include_favorites:
        headers.append("收藏名")
    if include_candidates:
        headers.append("候选名")
    headers.append("备注")

    if group_by_species:
        species_groups: Dict[str, List[Pet]] = {}
        for pet in pets:
            key = pet.species or "unknown"
            if key not in species_groups:
                species_groups[key] = []
            species_groups[key].append(pet)

        order = ["cat", "dog", "rabbit"]
        ordered_keys = [k for k in order if k in species_groups] + [
            k for k in species_groups if k not in order
        ]

        for sp_key in ordered_keys:
            sp_pets = species_groups[sp_key]
            sp_name = SPECIES_CN.get(sp_key, sp_key)
            writer.writerow([f"=== {sp_name}组 ({len(sp_pets)}只) ==="] + [""] * (len(headers) - 1))
            writer.writerow(headers)
            for pet in sp_pets:
                writer.writerow(_build_pet_row(pet, include_candidates, include_favorites, add_group=True))
            writer.writerow([])
    else:
        writer.writerow(headers)
        for pet in pets:
            writer.writerow(_build_pet_row(pet, include_candidates, include_favorites))

    return output.getvalue()


def _generate_json(pets: List[Pet], include_candidates: bool, include_favorites: bool,
                   template_data: dict, group_by_species: bool = False,
                   handover_summary: Optional[dict] = None) -> str:
    result = {
        "event_info": template_data if template_data else {},
        "total_count": len(pets),
    }

    if handover_summary:
        result["handover_summary"] = handover_summary

    if group_by_species:
        groups: Dict[str, List[dict]] = {}
        species_count: Dict[str, int] = {}
        for pet in pets:
            key = pet.species or "unknown"
            key_cn = SPECIES_CN.get(key, key)
            if key not in groups:
                groups[key] = []
                species_count[key] = 0
            groups[key].append(_build_pet_dict(pet, include_candidates, include_favorites))
            species_count[key] += 1

        result["groups"] = []
        order = ["cat", "dog", "rabbit"]
        ordered_keys = [k for k in order if k in groups] + [k for k in groups if k not in order]

        for k in ordered_keys:
            result["groups"].append({
                "species": k,
                "species_cn": SPECIES_CN.get(k, k),
                "count": species_count[k],
                "pets": groups[k],
            })
        result["pets"] = [_build_pet_dict(p, include_candidates, include_favorites) for p in pets]
    else:
        result["pets"] = [_build_pet_dict(p, include_candidates, include_favorites) for p in pets]

    return json.dumps(result, ensure_ascii=False, indent=2)


def _generate_excel(storage, pets: List[Pet], output: str, include_candidates: bool,
                    include_favorites: bool, template_data: dict,
                    group_by_species: bool = False,
                    handover_summary: Optional[dict] = None):
    import pandas as pd

    def _build_rows(pet_list: List[Pet]) -> list:
        rows = []
        for pet in pet_list:
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
                "备注": pet.notes if _is_valid_note(pet.notes) else "",
            }
            if include_favorites:
                row["收藏名"] = "、".join(pet.favorite_names)
            if include_candidates:
                row["候选名"] = "、".join(pet.candidate_names)
            rows.append(row)
        return rows

    try:
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            if handover_summary:
                hs = handover_summary
                summary_rows = []
                summary_rows.append({"项": "生成时间", "值": hs.get("generated_at", "")})
                summary_rows.append({"项": "负责人", "值": hs.get("owner") or ""})
                summary_rows.append({"项": "门店", "值": hs.get("store") or ""})
                summary_rows.append({"项": "任务ID", "值": hs.get("task_id") or ""})
                summary_rows.append({"项": "任务状态", "值": hs.get("task_status") or ""})
                summary_rows.append({"项": "总宠物数", "值": hs.get("total_count", 0)})
                summary_rows.append({"项": "已起名数", "值": hs.get("named_count", 0)})
                summary_rows.append({"项": "缺名额", "值": hs.get("missing_count", 0)})
                species_breakdown = hs.get("species_breakdown", {})
                for sp_key, sp_label in [("cat", "猫咪"), ("dog", "狗狗"), ("rabbit", "兔子")]:
                    sp_info = species_breakdown.get(sp_key, {"count": 0, "named_count": 0, "missing_count": 0})
                    summary_rows.append({
                        "项": f"{sp_label}数量",
                        "值": f"{sp_info['count']} (已起名{sp_info['named_count']}/缺{sp_info['missing_count']})"
                    })
                review_stats = hs.get("review_stats")
                if review_stats:
                    summary_rows.append({"项": "审核-已接受", "值": review_stats.get("accepted", 0)})
                    summary_rows.append({"项": "审核-已修改", "值": review_stats.get("modified", 0)})
                    summary_rows.append({"项": "审核-已拒绝", "值": review_stats.get("rejected", 0)})
                    summary_rows.append({"项": "审核-待审核", "值": review_stats.get("pending", 0)})
                pd.DataFrame(summary_rows).to_excel(writer, index=False, sheet_name="交接摘要")

            if group_by_species:
                species_groups: Dict[str, List[Pet]] = {}
                for pet in pets:
                    key = pet.species or "unknown"
                    if key not in species_groups:
                        species_groups[key] = []
                    species_groups[key].append(pet)

                order = ["cat", "dog", "rabbit"]
                ordered_keys = [k for k in order if k in species_groups] + [
                    k for k in species_groups if k not in order
                ]

                for sp_key in ordered_keys:
                    sp_pets = species_groups[sp_key]
                    sheet_name = f"{SPECIES_CN.get(sp_key, sp_key)}组"
                    pd.DataFrame(_build_rows(sp_pets)).to_excel(
                        writer, index=False, sheet_name=sheet_name[:31]
                    )

                pd.DataFrame(_build_rows(pets)).to_excel(
                    writer, index=False, sheet_name="全部名单"
                )
            else:
                pd.DataFrame(_build_rows(pets)).to_excel(
                    writer, index=False, sheet_name="宠物名单"
                )

            if template_data:
                event_rows = []
                all_keys = list(STANDARD_TEMPLATE_LABELS.keys()) + [
                    k for k in template_data.keys() if k not in STANDARD_TEMPLATE_LABELS
                ]
                for key in all_keys:
                    val = template_data.get(key, "")
                    if val:
                        cn_key = STANDARD_TEMPLATE_LABELS.get(key, key)
                        event_rows.append({"项目": cn_key, "内容": val})
                if event_rows:
                    pd.DataFrame(event_rows).to_excel(writer, index=False, sheet_name="活动信息")
    except ImportError:
        raise click.ClickException("需要安装 openpyxl: pip install openpyxl")
