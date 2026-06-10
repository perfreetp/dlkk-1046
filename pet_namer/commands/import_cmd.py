import click
import uuid
import pandas as pd
from pathlib import Path
from tabulate import tabulate

from ..models import Pet
from ..cli import pass_storage


AGE_MAP = {
    "幼年": 6,
    "青年": 18,
    "成年": 36,
    "老年": 84,
    "puppy": 6,
    "kitten": 6,
    "adult": 36,
    "senior": 84,
    "young": 12,
}

SPECIES_MAP = {
    "猫": "cat",
    "狗": "dog",
    "兔": "rabbit",
    "猫咪": "cat",
    "狗狗": "dog",
    "兔子": "rabbit",
    "cat": "cat",
    "dog": "dog",
    "rabbit": "rabbit",
}

GENDER_MAP = {
    "公": "male",
    "母": "female",
    "男": "male",
    "女": "female",
    "male": "male",
    "female": "female",
    "中性": "neutral",
    "unknown": "neutral",
}


@click.command("import")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--format", "fmt",
              type=click.Choice(["auto", "csv", "xlsx", "xls"]),
              default="auto", help="文件格式")
@click.option("--sheet", default=0, help="Excel工作表名称或索引")
@click.option("--batch", help="为导入的宠物设置批次号")
@click.option("--source", help="设置来源")
@click.option("--dry-run", is_flag=True, help="预览导入结果，不实际保存")
@click.option("--encoding", default="utf-8", help="CSV文件编码")
@pass_storage
def import_cmd(storage, file_path, fmt, sheet, batch, source, dry_run, encoding):
    """从表格文件导入宠物信息
    
    支持的列名:
    物种, species, 性别, gender, 年龄, age, 月龄,
    毛色, coat_color, color, 性格, personality,
    标签, tags, 备注, notes, 已有名字, name,
    批次, batch, 来源, source
    """
    
    file_path = Path(file_path)
    
    if fmt == "auto":
        suffix = file_path.suffix.lower()
        if suffix in [".csv"]:
            fmt = "csv"
        elif suffix in [".xlsx", ".xls"]:
            fmt = "xlsx"
        else:
            raise click.ClickException(f"不支持的文件格式: {suffix}")
    
    click.echo(f"正在读取文件: {file_path}")
    
    try:
        if fmt == "csv":
            df = pd.read_csv(file_path, encoding=encoding)
        else:
            df = pd.read_excel(file_path, sheet_name=sheet)
    except Exception as e:
        raise click.ClickException(f"读取文件失败: {str(e)}")
    
    click.echo(f"读取到 {len(df)} 行数据")
    click.echo(f"列名: {', '.join(df.columns.tolist())}")
    click.echo()
    
    pets = []
    
    for idx, row in df.iterrows():
        pet = _row_to_pet(row, batch, source)
        if pet:
            pets.append(pet)
    
    if not pets:
        raise click.ClickException("没有解析到有效的宠物数据")
    
    table_data = []
    for i, pet in enumerate(pets, 1):
        details = []
        if pet.species:
            details.append(pet.species)
        if pet.gender:
            details.append(pet.gender)
        if pet.age:
            details.append(pet.age)
        if pet.coat_color:
            details.append(pet.coat_color)
        if pet.personality:
            details.append(",".join(pet.personality))
        table_data.append([i, pet.id[:8], " | ".join(details), pet.selected_name or "-"])
    
    click.echo(click.style("=== 预览导入数据 ===", fg="cyan", bold=True))
    click.echo(tabulate(table_data, headers=["#", "ID", "信息", "已有名字"], tablefmt="simple"))
    
    if dry_run:
        click.echo(f"\n预览模式，未实际保存。去掉 --dry-run 执行导入")
        return
    
    if not click.confirm(f"\n确认导入 {len(pets)} 只宠物？", default=True):
        click.echo("已取消导入")
        return
    
    for pet in pets:
        storage.add_pet(pet)
    
    click.echo(click.style(f"\n成功导入 {len(pets)} 只宠物！", fg="green"))
    
    stats = storage.load_stats()
    stats.total_pets = len(storage.load_pets())
    stats.named_pets = sum(1 for p in storage.load_pets() if p.selected_name)
    storage.save_stats(stats)


def _row_to_pet(row, batch=None, source=None):
    species = _get_value(row, ["物种", "species", "品种", "breed"])
    if species:
        species = SPECIES_MAP.get(str(species).strip().lower(), str(species).strip().lower())
    
    if not species:
        return None
    
    gender = _get_value(row, ["性别", "gender", "sex"])
    if gender:
        gender = str(gender).strip()
        gender = GENDER_MAP.get(gender.lower(), gender)
    
    age = _get_value(row, ["年龄", "age"])
    age_months = _get_value(row, ["月龄", "age_months", "months"])
    
    if age_months is not None:
        try:
            age_months = int(age_months)
        except (ValueError, TypeError):
            age_months = None
    
    if age_months is None and age:
        age_str = str(age).strip().lower()
        if age_str in AGE_MAP:
            age_months = AGE_MAP[age_str]
        else:
            age_months = _parse_age(str(age).strip())
    
    coat_color = _get_value(row, ["毛色", "coat_color", "color", "颜色"])
    if coat_color:
        coat_color = str(coat_color).strip()
    
    personality = _get_value(row, ["性格", "personality", "标签", "tags", "特点"])
    personality_list = []
    if personality:
        if isinstance(personality, str):
            personality_list = [p.strip() for p in personality.replace("，", ",").split(",") if p.strip()]
        elif isinstance(personality, list):
            personality_list = [str(p).strip() for p in personality]
    
    pet_batch = _get_value(row, ["批次", "batch"])
    if not pet_batch:
        pet_batch = batch
    
    pet_source = _get_value(row, ["来源", "source"])
    if not pet_source:
        pet_source = source
    
    selected_name = _get_value(row, ["名字", "name", "已有名字", "现用名"])
    if selected_name:
        selected_name = str(selected_name).strip()
        if not selected_name or str(selected_name).lower() in ["nan", "none", "无", ""]:
            selected_name = None
    
    notes = _get_value(row, ["备注", "notes", "说明"])
    if notes:
        notes = str(notes).strip()
    
    return Pet(
        id=str(uuid.uuid4()),
        species=species,
        gender=gender,
        age=str(age) if age else None,
        age_months=age_months,
        coat_color=coat_color,
        personality=personality_list,
        batch=str(pet_batch) if pet_batch else None,
        source=str(pet_source) if pet_source else None,
        selected_name=selected_name,
        notes=notes,
    )


def _get_value(row, *keys):
    if len(keys) == 1 and isinstance(keys[0], (list, tuple)):
        keys = keys[0]
    for key in keys:
        key_str = str(key)
        if key_str in row and pd.notna(row[key_str]):
            return row[key_str]
        for col in row.index:
            if str(col).lower() == key_str.lower():
                if pd.notna(row[col]):
                    return row[col]
    return None


def _parse_age(age_str):
    if not age_str:
        return None
    age_str = age_str.lower().strip()
    
    import re
    
    m = re.match(r"(\d+)\s*(month|months|m)", age_str)
    if m:
        return int(m.group(1))
    
    m = re.match(r"(\d+)\s*(year|years|y)", age_str)
    if m:
        return int(m.group(1)) * 12
    
    m = re.match(r"(\d+)\s*岁", age_str)
    if m:
        return int(m.group(1)) * 12
    
    m = re.match(r"(\d+)\s*个月", age_str)
    if m:
        return int(m.group(1))
    
    return None
