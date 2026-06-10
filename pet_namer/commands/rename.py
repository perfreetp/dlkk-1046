import click
from tabulate import tabulate
from typing import List, Dict, Tuple

from ..models import Pet, GenerationParams
from ..generator import NameGenerator
from ..cli import pass_storage


@click.command()
@click.option("--pet-id", "pet_ids", multiple=True, help="指定宠物ID，可多次指定")
@click.option("--batch", help="按批次筛选")
@click.option("--species", type=click.Choice(["cat", "dog", "rabbit", "all"]), default="all", help="按物种筛选")
@click.option("--from-name", help="要替换的旧名字")
@click.option("--to-name", help="新的名字")
@click.option("--pattern", help="按模式匹配名字 (支持通配符 *?)")
@click.option("--replace-with", help="替换为的新名字")
@click.option("--contains", help="包含特定字符串的名字")
@click.option("--list-problems/--no-list-problems", default=False, help="列出有问题的名字")
@click.option("--auto-regenerate/--no-auto-regenerate", default=False, help="自动为受影响的宠物重新生成名字")
@click.option("--count", type=int, default=5, help="重新生成时的候选数量")
@click.option("--style", type=click.Choice(["cute", "traditional", "western", "cool", "literary", "all"]), default="all", help="重新生成的名字风格")
@click.option("--language", type=click.Choice(["zh", "en", "all"]), default="all", help="重新生成的语言")
@click.option("--dry-run", is_flag=True, help="预览修改，不实际保存")
@pass_storage
def rename(storage, pet_ids, batch, species, from_name, to_name, pattern,
           replace_with, contains, list_problems, auto_regenerate, count,
           style, language, dry_run):
    """批量替换不合适的名字"""
    
    pets = storage.load_pets()
    
    if pet_ids:
        pets = [p for p in pets if p.id in pet_ids]
    
    if batch:
        pets = [p for p in pets if p.batch == batch]
    
    if species and species != "all":
        pets = [p for p in pets if p.species == species]
    
    if not pets:
        raise click.ClickException("没有找到符合条件的宠物")
    
    if list_problems:
        _list_problematic_names(storage, pets)
        return
    
    replacements = []
    
    if from_name and to_name:
        replacements = _find_replacements(pets, from_name, to_name)
    elif pattern and replace_with:
        replacements = _find_pattern_replacements(pets, pattern, replace_with)
    elif contains:
        replacements = _find_contains_replacements(pets, contains, replace_with)
    else:
        click.echo(click.style("=== 当前宠物名字状态 ===", fg="cyan", bold=True))
        _list_all_names(pets)
        click.echo("\n使用 --from-name / --to-name 或 --pattern / --replace-with 进行批量替换")
        return
    
    if not replacements:
        click.echo("没有找到需要替换的名字")
        return
    
    _display_replacements(replacements, dry_run)
    
    if dry_run:
        click.echo("\n预览模式，未实际修改。去掉 --dry-run 执行替换")
        return
    
    if not click.confirm(f"\n确认替换 {len(replacements)} 个名字？", default=True):
        click.echo("已取消")
        return
    
    pet_map = {}
    for pet, name_type, old_name, new_name in replacements:
        if pet.id not in pet_map:
            pet_map[pet.id] = pet
        p = pet_map[pet.id]
        if name_type == "selected":
            p.selected_name = new_name
        if name_type in ["candidate", "both"]:
            if old_name in p.candidate_names:
                p.candidate_names = [new_name if n == old_name else n for n in p.candidate_names]
        if name_type in ["favorite", "both"]:
            if old_name in p.favorite_names:
                p.favorite_names = [new_name if n == old_name else n for n in p.favorite_names]
    
    modified_pets = list(pet_map.values())
    unique_pet_ids = set()
    for pet in modified_pets:
        if pet.id not in unique_pet_ids:
            unique_pet_ids.add(pet.id)
            storage.update_pet(pet)
    
    click.echo(click.style(f"\n成功替换 {len(replacements)} 个名字，涉及 {len(modified_pets)} 只宠物！", fg="green"))
    
    if auto_regenerate:
        _regenerate_for_affected(storage, modified_pets, count, style, language)
    
    stats = storage.load_stats()
    stats.named_pets = sum(1 for p in storage.load_pets() if p.selected_name)
    storage.save_stats(stats)


def _list_all_names(pets: List[Pet]):
    table_data = []
    for pet in pets:
        names = []
        if pet.selected_name:
            names.append(f"✓ {pet.selected_name}")
        if pet.favorite_names:
            names.append(f"★ {', '.join(pet.favorite_names)}")
        if pet.candidate_names:
            names.append(f"○ {', '.join(pet.candidate_names)}")
        
        table_data.append([
            pet.id[:8],
            f"{pet.species} {pet.gender or ''}",
            pet.batch or "-",
            "\n".join(names) if names else "(无名字)"
        ])
    
    click.echo(tabulate(
        table_data,
        headers=["ID", "信息", "批次", "名字"],
        tablefmt="simple"
    ))


def _list_problematic_names(storage, pets: List[Pet]):
    name_library = storage.load_names()
    generator = NameGenerator(name_library)
    
    all_names = []
    for pet in pets:
        if pet.selected_name:
            all_names.append(pet.selected_name)
        all_names.extend(pet.favorite_names)
        all_names.extend(pet.candidate_names)
    
    click.echo(click.style("=== 问题名字检查 ===", fg="cyan", bold=True))
    
    duplicates = generator.find_duplicates(all_names)
    if duplicates:
        click.echo("\n重复名字:")
        for name_lower, variants in duplicates.items():
            click.echo(f"  {', '.join(set(variants))}")
    
    similar = generator.find_similar(list(set(all_names)))
    if similar:
        click.echo("\n发音相近名字:")
        for n1, n2, sim in similar:
            click.echo(f"  {n1} ↔ {n2} (相似度: {sim:.2f})")
    
    if not duplicates and not similar:
        click.echo("未发现问题名字 ✅")
    
    click.echo()


def _find_replacements(pets: List[Pet], from_name: str, to_name: str) -> List[Tuple[Pet, str, str, str]]:
    replacements = []
    from_lower = from_name.lower()
    
    for pet in pets:
        if pet.selected_name and pet.selected_name.lower() == from_lower:
            replacements.append((pet, "selected", pet.selected_name, to_name))
        
        for name in pet.candidate_names:
            if name.lower() == from_lower:
                replacements.append((pet, "candidate", name, to_name))
        
        for name in pet.favorite_names:
            if name.lower() == from_lower:
                replacements.append((pet, "favorite", name, to_name))
    
    return replacements


def _find_pattern_replacements(pets: List[Pet], pattern: str, replace_with: str) -> List[Tuple[Pet, str, str, str]]:
    import fnmatch
    replacements = []
    
    for pet in pets:
        if pet.selected_name and fnmatch.fnmatch(pet.selected_name.lower(), pattern.lower()):
            new_name = pet.selected_name.lower().replace(pattern.lower().replace("*", ""), replace_with)
            replacements.append((pet, "selected", pet.selected_name, replace_with))
        
        for name in pet.candidate_names:
            if fnmatch.fnmatch(name.lower(), pattern.lower()):
                replacements.append((pet, "candidate", name, replace_with))
        
        for name in pet.favorite_names:
            if fnmatch.fnmatch(name.lower(), pattern.lower()):
                replacements.append((pet, "favorite", name, replace_with))
    
    return replacements


def _find_contains_replacements(pets: List[Pet], contains: str, replace_with: str) -> List[Tuple[Pet, str, str, str]]:
    replacements = []
    contains_lower = contains.lower()
    
    for pet in pets:
        if pet.selected_name and contains_lower in pet.selected_name.lower():
            new_name = pet.selected_name.lower().replace(contains_lower, replace_with.lower())
            replacements.append((pet, "selected", pet.selected_name, new_name.capitalize()))
        
        for name in pet.candidate_names:
            if contains_lower in name.lower():
                new_name = name.lower().replace(contains_lower, replace_with.lower())
                replacements.append((pet, "candidate", name, new_name.capitalize()))
        
        for name in pet.favorite_names:
            if contains_lower in name.lower():
                new_name = name.lower().replace(contains_lower, replace_with.lower())
                replacements.append((pet, "favorite", name, new_name.capitalize()))
    
    return replacements


def _display_replacements(replacements, dry_run):
    table_data = []
    for i, (pet, name_type, old_name, new_name) in enumerate(replacements, 1):
        table_data.append([
            i,
            pet.id[:8],
            name_type,
            old_name,
            new_name
        ])
    
    click.echo(click.style("\n=== 待替换列表 ===", fg="cyan", bold=True))
    click.echo(tabulate(
        table_data,
        headers=["#", "宠物ID", "类型", "旧名字", "新名字"],
        tablefmt="simple"
    ))


def _regenerate_for_affected(storage, pets: List[Pet], count: int, style: str, language: str):
    click.echo(click.style(f"\n=== 自动重新生成候选名 ===", fg="cyan", bold=True))
    click.echo(f"目标宠物数: {len(pets)}")
    click.echo(f"每只候选数: {count}")
    click.echo()
    
    name_library = storage.load_names()
    generator = NameGenerator(name_library)
    
    params = GenerationParams(
        candidates_per_pet=count,
        style=None if style == "all" else style,
        language=None if language == "all" else language,
        avoid_similar=True,
        exclude_used=True,
    )
    
    used_names = set(storage.get_used_names())
    success_count = 0
    failed_pets = []
    
    for i, pet in enumerate(pets, 1):
        pet_label = f"[{i}/{len(pets)}] {pet.id[:8]} ({pet.species})"
        try:
            current_used = list(used_names)
            candidates = generator.generate_for_pet(pet, params, current_used, count)
            if candidates:
                pet.candidate_names = candidates
                storage.update_pet(pet)
                used_names.update(candidates)
                click.echo(f"  ✅ {pet_label}: {', '.join(candidates)}")
                success_count += 1
            else:
                click.echo(f"  ⚠️  {pet_label}: 未找到合适候选名")
                failed_pets.append(pet.id[:8])
        except Exception as e:
            click.echo(f"  ❌ {pet_label}: 生成失败 - {str(e)}")
            failed_pets.append(pet.id[:8])
    
    click.echo()
    click.echo(click.style(f"重新生成完成！成功: {success_count}/{len(pets)}", fg="green"))
    if failed_pets:
        click.echo(click.style(f"失败/未生成: {', '.join(failed_pets)}", fg="yellow"))
        click.echo("提示: 可减少 --count 或放宽 --style/--language 后重试")
    
    return success_count, failed_pets
