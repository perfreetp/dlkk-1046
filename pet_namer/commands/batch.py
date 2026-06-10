import click
import json
import uuid
import datetime as _dt
from pathlib import Path
from tabulate import tabulate
from typing import List, Tuple, Dict, Optional

from ..models import (
    Pet, GenerationParams, GenerationRecord, NameEntry,
    BatchTaskRecord, BatchTaskStep,
)
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


def _clean_str(val):
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    low = s.lower()
    if low in ["nan", "none", "null", "n/a", "na", "-", "--"]:
        return None
    return s


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

STEP_LABELS = {
    "import": "导入宠物信息",
    "generate": "生成候选名字",
    "recommend": "自动挑选推荐名",
    "export": "导出领养名单",
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
@click.option("--organizer", help="主办方/救助站名称（导出模板字段）")
@click.option("--note", "event_note", help="活动说明/备注（导出模板字段）")
@click.option("--qr-code", help="二维码/报名链接（导出模板字段）")
@click.option("--custom-field", "custom_fields", multiple=True,
              help="自定义模板字段 key=value，可多次指定，如 wechat=adopt2024")
@click.option("--template", help="模板配置文件（YAML/JSON）")
@click.option("--yes", "-y", is_flag=True, help="跳过所有确认步骤")
@click.option("--list-tasks", "list_tasks", is_flag=True, help="列出所有批量任务记录")
@click.option("--show-task", "show_task_id", type=str, help="查看指定任务的详细记录")
@click.option("--rerun-failed", "rerun_task_id", type=str,
              help="重跑指定任务中失败的宠物（只重跑生成和之后的步骤）")
@pass_storage
def batch(storage, import_file, batch_name, count, style, language, species,
          recommend, auto_select, export_fmt, output, named_only, group_by_species,
          include_candidates, include_favorites, contact_phone, location,
          event_date, event_name, organizer, event_note, qr_code, custom_fields,
          template, yes,
          list_tasks, show_task_id, rerun_task_id):
    """批量任务模式：导入→生成候选→自动推荐→导出海报"""

    if list_tasks:
        _list_tasks(storage)
        return

    if show_task_id:
        _show_task(storage, show_task_id)
        return

    if rerun_task_id:
        _rerun_failed(storage, rerun_task_id, count, style, language, recommend, auto_select,
                      export_fmt, output, named_only, group_by_species,
                      include_candidates, include_favorites,
                      contact_phone, location, event_date, event_name, template, yes)
        return

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

    task = BatchTaskRecord(
        id=uuid.uuid4().hex[:12],
        timestamp=_dt.datetime.now().isoformat(),
        status="running",
        params={
            "import_file": import_file,
            "batch_name": batch_name,
            "count": count,
            "style": style,
            "language": language,
            "species": species,
            "recommend": recommend,
            "auto_select": auto_select,
            "export_format": export_fmt,
        },
    )
    storage.add_task(task)

    try:
        click.echo(click.style("=" * 60, fg="cyan", bold=True))
        click.echo(click.style(f"🐾 宠物批量起名任务 (ID: {task.id}) 🐾", fg="cyan", bold=True))
        click.echo(click.style("=" * 60, fg="cyan", bold=True))
        click.echo()

        target_pets = []

        step_import = BatchTaskStep(name="import", started_at=_dt.datetime.now().isoformat())
        if import_file:
            click.echo(click.style("【步骤 1/4】导入宠物信息", fg="yellow", bold=True))
            imported_pets = _batch_import(storage, import_file, batch_name, yes)
            target_pets = imported_pets
            step_import.total_count = len(target_pets)
            step_import.success_count = len(target_pets)
            step_import.extra = {"from_file": import_file}
            click.echo()
        else:
            click.echo(click.style("【步骤 1/4】选择目标宠物", fg="yellow", bold=True))
            pets = storage.load_pets()
            if species and species != "all":
                pets = [p for p in pets if p.species == species]
            if not pets:
                raise click.ClickException("没有符合条件的宠物，请先使用 --import-file 导入")
            target_pets = pets
            step_import.total_count = len(target_pets)
            step_import.success_count = len(target_pets)
            step_import.extra = {"filter_species": species}
            click.echo(f"  已选择 {len(target_pets)} 只宠物（物种筛选: {species}）")
            click.echo()

        step_import.finished_at = _dt.datetime.now().isoformat()
        task.steps.append(step_import)
        storage.update_task(task)

        if not target_pets:
            raise click.ClickException("没有可处理的宠物")

        params = GenerationParams(
            candidates_per_pet=count,
            style=None if style == "all" else style,
            language=None if language == "all" else language,
            avoid_similar=True,
            exclude_used=True,
        )

        click.echo(click.style("【步骤 2/4】生成候选名字", fg="yellow", bold=True))
        step_gen = BatchTaskStep(name="generate", started_at=_dt.datetime.now().isoformat())
        results, generated_pets, failed_pets, gen_record_id = _batch_generate(
            storage, target_pets, params
        )
        step_gen.total_count = len(target_pets)
        step_gen.success_count = len(generated_pets)
        step_gen.failed_ids = [pid for pid, _ in failed_pets]
        step_gen.extra = {"generation_record": gen_record_id}
        step_gen.finished_at = _dt.datetime.now().isoformat()
        task.steps.append(step_gen)
        task.generation_record_id = gen_record_id
        storage.update_task(task)
        click.echo()

        click.echo(click.style("【步骤 3/4】自动挑选推荐名", fg="yellow", bold=True))
        step_rec = BatchTaskStep(name="recommend", started_at=_dt.datetime.now().isoformat())
        name_library = storage.load_names()
        recommendations = _batch_recommend(
            storage, generated_pets, results, name_library, recommend, auto_select
        )
        step_rec.total_count = len(generated_pets)
        step_rec.success_count = sum(1 for r in recommendations if r["recommended"])
        step_rec.extra = {"strategy": recommend, "auto_select": auto_select}
        step_rec.finished_at = _dt.datetime.now().isoformat()
        task.steps.append(step_rec)
        storage.update_task(task)
        click.echo()

        export_result = None
        if export_fmt != "none":
            click.echo(click.style("【步骤 4/4】导出领养名单", fg="yellow", bold=True))
            step_exp = BatchTaskStep(name="export", started_at=_dt.datetime.now().isoformat())
            export_pets = generated_pets
            if named_only:
                export_pets = [p for p in export_pets if p.selected_name]

            export_result = _batch_export(
                storage, export_pets, export_fmt, output, include_candidates,
                include_favorites, group_by_species, template_data
            )
            step_exp.total_count = len(export_pets)
            step_exp.success_count = len(export_pets)
            step_exp.extra = {"format": export_fmt, "output_file": export_result}
            step_exp.finished_at = _dt.datetime.now().isoformat()
            task.steps.append(step_exp)
            task.export_file = export_result
            storage.update_task(task)
            click.echo()

        task.status = "completed"
        _show_task_summary(task, failed_pets)

    except Exception as e:
        task.status = f"failed: {str(e)[:100]}"
        storage.update_task(task)
        raise

    storage.update_task(task)
    click.echo(click.style(f"任务ID: {task.id}（可用 --show-task {task.id[:8]} 查看详情）", fg="cyan"))


def _list_tasks(storage):
    tasks = storage.load_tasks()
    if not tasks:
        click.echo("暂无批量任务记录")
        return

    click.echo(click.style("=== 批量任务列表 ===", fg="cyan", bold=True))
    table_data = []
    for i, task in enumerate(reversed(tasks[-20:]), 1):
        ts = task.timestamp.replace("T", " ").split(".")[0]
        import_count = 0
        gen_count = 0
        rec_count = 0
        for step in task.steps:
            if step.name == "import":
                import_count = step.success_count
            elif step.name == "generate":
                gen_count = step.success_count
            elif step.name == "recommend":
                rec_count = step.success_count

        fmt = task.params.get("export_format", "-")
        status_color = {"completed": "green", "running": "yellow"}.get(
            task.status, "red"
        ) if task.status == "completed" else None
        status_display = click.style(task.status, fg=status_color) if status_color else task.status

        table_data.append([
            len(tasks) - i + 1,
            task.id[:8],
            ts,
            import_count,
            gen_count,
            rec_count,
            fmt,
            status_display,
        ])

    click.echo(tabulate(
        table_data,
        headers=["#", "任务ID", "时间", "导入", "生成", "推荐", "导出", "状态"],
        tablefmt="simple"
    ))
    click.echo()
    click.echo("使用 `pet-namer batch --show-task <任务ID>` 查看详情")
    click.echo("使用 `pet-namer batch --rerun-failed <任务ID>` 重跑失败项")


def _show_task(storage, task_id):
    task = storage.get_task(task_id)
    if not task:
        raise click.ClickException(f"找不到任务: {task_id}")

    click.echo(click.style(f"=== 任务详情 [{task.id}] ===", fg="cyan", bold=True))
    ts = task.timestamp.replace("T", " ").split(".")[0]
    click.echo(f"创建时间: {ts}")
    click.echo(f"状态: {task.status}")

    if task.export_file:
        click.echo(f"导出文件: {task.export_file}")
    if task.generation_record_id:
        click.echo(f"生成记录ID: {task.generation_record_id}")
    click.echo()

    click.echo(click.style("📋 任务参数", fg="yellow"))
    param_table = []
    param_labels = {
        "import_file": "导入文件", "batch_name": "批次号",
        "count": "每只候选数", "style": "风格", "language": "语言",
        "species": "物种筛选", "recommend": "推荐策略",
        "auto_select": "自动设为正式名", "export_format": "导出格式",
    }
    for k, v in task.params.items():
        label = param_labels.get(k, k)
        val = v if v is not None else "-"
        if k == "auto_select":
            val = "是" if val else "否"
        if k == "recommend" and val in RECOMMEND_LABELS:
            val = RECOMMEND_LABELS[val]
        param_table.append([label, val])
    click.echo(tabulate(param_table, tablefmt="simple"))
    click.echo()

    click.echo(click.style("📈 步骤执行情况", fg="yellow"))
    step_table = []
    all_failed = []
    for step in task.steps:
        label = STEP_LABELS.get(step.name, step.name)
        start = step.started_at.replace("T", " ").split(".")[0] if step.started_at else "-"
        duration = ""
        if step.started_at and step.finished_at:
            try:
                s = _dt.datetime.fromisoformat(step.started_at)
                e = _dt.datetime.fromisoformat(step.finished_at)
                dur_sec = (e - s).total_seconds()
                duration = f"{dur_sec:.1f}s"
            except Exception:
                duration = "-"

        result = f"{step.success_count}/{step.total_count}"
        if step.failed_ids:
            result += f" ❌{len(step.failed_ids)}"
            all_failed.extend([(label, fid) for fid in step.failed_ids])

        extra_info = ""
        if step.name == "export" and step.extra.get("output_file"):
            extra_info = f" → {step.extra['output_file']}"

        step_table.append([label, start, duration, result, extra_info])

    click.echo(tabulate(
        step_table,
        headers=["步骤", "开始时间", "耗时", "结果", "备注"],
        tablefmt="simple"
    ))
    click.echo()

    if all_failed:
        click.echo(click.style("⚠️  失败的宠物ID", fg="yellow"))
        for step_name, pid in all_failed:
            click.echo(f"  - [{step_name}] {pid}")
        click.echo()


def _show_task_summary(task: BatchTaskRecord, failed_pets: List[Tuple[str, str]]):
    click.echo(click.style("=" * 60, fg="cyan", bold=True))
    click.echo(click.style("📊 任务总结", fg="yellow", bold=True))

    summary = []
    for step in task.steps:
        label = STEP_LABELS.get(step.name, step.name)
        summary.append([label, f"{step.success_count}/{step.total_count}"])

    if task.export_file:
        summary.append(["导出文件", task.export_file])

    click.echo(tabulate(summary, tablefmt="simple"))

    if failed_pets:
        click.echo()
        click.echo(click.style("⚠️  生成失败的宠物:", fg="yellow"))
        for pid, reason in failed_pets:
            click.echo(f"  - {pid[:8]}: {reason}")
        click.echo(click.style(
            f"提示: 使用 `pet-namer batch --rerun-failed {task.id[:8]}` 仅重跑失败的宠物",
            fg="cyan"
        ))

    click.echo()
    click.echo(click.style("✅ 批量任务完成！", fg="green", bold=True))


def _rerun_failed(storage, task_id, count, style, language, recommend, auto_select,
                  export_fmt, output, named_only, group_by_species,
                  include_candidates, include_favorites,
                  contact_phone, location, event_date, event_name, template, yes):
    orig_task = storage.get_task(task_id)
    if not orig_task:
        raise click.ClickException(f"找不到任务: {task_id}")

    failed_ids = set()
    for step in orig_task.steps:
        failed_ids.update(step.failed_ids)

    if not failed_ids:
        click.echo(click.style("原任务中没有失败的宠物，全部成功 ✅", fg="green"))
        return

    all_pets = storage.load_pets()
    pets = [p for p in all_pets if p.id in failed_ids]

    if not pets:
        raise click.ClickException(f"找不到失败的宠物 (失败ID: {', '.join(failed_ids)})")

    click.echo(click.style(f"🚀 重跑任务 {orig_task.id[:8]} 中失败的 {len(pets)} 只宠物...", fg="cyan", bold=True))
    click.echo(f"  失败宠物ID: {', '.join(p.id[:8] for p in pets)}")
    click.echo()

    template_data = _load_template(template)
    template_data["contact_phone"] = contact_phone or template_data.get("contact_phone", "")
    template_data["location"] = location or template_data.get("location", "")
    template_data["event_date"] = event_date or template_data.get("event_date", "")
    template_data["event_name"] = event_name or template_data.get("event_name", "")

    orig_params = orig_task.params
    count = count if count != 5 else orig_params.get("count", count)
    style = style if style != "all" else orig_params.get("style", style)
    language = language if language != "all" else orig_params.get("language", language)
    recommend = recommend if recommend != "top_score" else orig_params.get("recommend", recommend)
    export_fmt = export_fmt if export_fmt != "poster" else orig_params.get("export_format", export_fmt)
    if not auto_select:
        auto_select = orig_params.get("auto_select", auto_select)

    gen_params = GenerationParams(
        candidates_per_pet=count,
        style=None if style == "all" else style,
        language=None if language == "all" else language,
        avoid_similar=True,
        exclude_used=True,
    )

    click.echo(click.style("【步骤 1/3】重新生成候选名字", fg="yellow", bold=True))
    results, generated_pets, failed_pets, _ = _batch_generate(storage, pets, gen_params)
    click.echo()

    click.echo(click.style("【步骤 2/3】自动挑选推荐名", fg="yellow", bold=True))
    name_library = storage.load_names()
    _ = _batch_recommend(storage, generated_pets, results, name_library, recommend, auto_select)
    click.echo()

    export_result = None
    if export_fmt != "none":
        click.echo(click.style("【步骤 3/3】导出领养名单", fg="yellow", bold=True))
        export_pets = generated_pets
        if named_only:
            export_pets = [p for p in export_pets if p.selected_name]
        if not output:
            output = f"rerun_{orig_task.id[:8]}_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.{export_fmt if export_fmt != 'excel' else 'xlsx'}"

        export_result = _batch_export(
            storage, export_pets, export_fmt, output, include_candidates,
            include_favorites, group_by_species, template_data
        )

    click.echo()
    click.echo(click.style(f"✅ 重跑完成！成功 {len(generated_pets)}/{len(pets)}", fg="green", bold=True))
    if export_result:
        click.echo(f"导出文件: {export_result}")
    if failed_pets:
        click.echo(click.style("仍失败的宠物:", fg="yellow"))
        for pid, reason in failed_pets:
            click.echo(f"  - {pid[:8]}: {reason}")


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
            if key in row and row[key] is not None:
                cleaned = _clean_str(row[key])
                if cleaned:
                    return cleaned
        return None

    for _, row in df.iterrows():
        species = _normalize_species(_get_value(row, "物种", "species", "品种", "breed"))
        gender = _normalize_gender(_get_value(row, "性别", "gender", "sex"))
        age_raw = _get_value(row, "年龄", "age")
        age_months_raw = _get_value(row, "月龄", "age_months", "months", "month")

        age, age_months = _parse_age(age_raw, age_months_raw)
        coat_color = _get_value(row, "毛色", "coat_color", "颜色", "color")
        personality_raw = _get_value(row, "性格", "personality", "标签", "tags", "特点")
        personality = []
        if personality_raw:
            personality = [p.strip() for p in personality_raw.replace("，", ",").split(",") if p.strip()]

        source_batch = _get_value(row, "批次", "batch")
        source = _get_value(row, "来源", "source", "origin")
        notes = _get_value(row, "备注", "notes", "remark", "说明")

        if not source_batch and batch_name:
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

    click.echo()
    click.echo(click.style("  === 预览导入数据 ===", fg="cyan"))
    table_data = []
    for i, pet in enumerate(pets, 1):
        info_parts = [pet.species or "-", pet.gender or "-", pet.age or "-"]
        if pet.coat_color:
            info_parts.append(pet.coat_color)
        if pet.personality:
            info_parts.append(",".join(pet.personality))
        if pet.batch:
            info_parts.append(f"批次:{pet.batch}")
        info = " | ".join(info_parts)
        extra_parts = []
        if pet.source:
            extra_parts.append(f"来源:{pet.source}")
        if pet.notes:
            extra_parts.append(f"备注:{pet.notes}")
        extra = "; ".join(extra_parts)
        table_data.append([i, pet.id[:8], info, extra or "-"])

    click.echo(tabulate(
        table_data,
        headers=["#", "ID", "信息", "来源/备注"],
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
    Dict[str, List[str]], List[Pet], List[Tuple[str, str]], str
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
            candidates = generator.generate_for_pet(
                pet, params, current_used, params.candidates_per_pet
            )

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

    record = GenerationRecord(
        id=uuid.uuid4().hex[:12],
        timestamp=_dt.datetime.now().isoformat(),
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

    return results, generated_pets, failed, record.id


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
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        base = default_outputs.get(fmt, "adoption_output")
        if fmt == "excel":
            output = f"adoption_list_{ts}.xlsx"
        else:
            p = Path(base)
            output = f"{p.stem}_{ts}{p.suffix}"

    if fmt == "poster":
        content = _generate_poster(pets, include_candidates, include_favorites, group_by_species, template_data)
        Path(output).write_text(content, encoding="utf-8")
    elif fmt == "csv":
        content = _generate_csv(pets, include_candidates, include_favorites, template_data, group_by_species)
        Path(output).write_text(content, encoding="utf-8")
    elif fmt == "json":
        content = _generate_json(pets, include_candidates, include_favorites, template_data, group_by_species)
        Path(output).write_text(content, encoding="utf-8")
    elif fmt == "excel":
        _generate_excel(storage, pets, output, include_candidates, include_favorites, template_data, group_by_species)

    click.echo(click.style(f"  ✅ 已导出 {len(pets)} 只宠物到: {output}", fg="green"))
    return output
