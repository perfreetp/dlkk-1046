import click
from tabulate import tabulate
from typing import List

from ..models import Pet
from ..generator import NameGenerator
from ..cli import pass_storage


@click.command()
@click.option("--pet-id", "pet_ids", multiple=True, help="指定宠物ID，可多次指定")
@click.option("--batch", help="按批次筛选")
@click.option("--species", type=click.Choice(["cat", "dog", "rabbit", "all"]), default="all", help="按物种筛选")
@click.option("--list", "list_mode", is_flag=True, help="列出所有宠物及其候选名字")
@click.option("--select", is_flag=True, help="从收藏中选择正式名")
@click.option("--add", multiple=True, help="手动添加名字到收藏，格式: pet_id:name")
@click.option("--remove", multiple=True, help="从收藏中移除名字，格式: pet_id:name")
@click.option("--set-name", multiple=True, help="设置正式名，格式: pet_id:name")
@pass_storage
def favorite(storage, pet_ids, batch, species, list_mode, select, add, remove, set_name):
    """管理宠物收藏名字和候选名"""
    
    pets = storage.load_pets()
    
    if pet_ids:
        pets = [p for p in pets if p.id in pet_ids]
    
    if batch:
        pets = [p for p in pets if p.batch == batch]
    
    if species and species != "all":
        pets = [p for p in pets if p.species == species]
    
    if not pets:
        raise click.ClickException("没有找到符合条件的宠物")
    
    if list_mode:
        _list_favorites(storage, pets)
        return
    
    if add:
        for item in add:
            _add_favorite(storage, item)
        return
    
    if remove:
        for item in remove:
            _remove_favorite(storage, item)
        return
    
    if set_name:
        for item in set_name:
            _set_selected_name(storage, item)
        return
    
    if select:
        _select_from_favorites(storage, pets)
        return
    
    _list_favorites(storage, pets)


def _list_favorites(storage, pets: List[Pet]):
    name_library = storage.load_names()
    generator = NameGenerator(name_library)
    
    table_data = []
    for pet in pets:
        info_parts = [pet.id[:8], pet.species]
        if pet.gender:
            info_parts.append(pet.gender)
        if pet.coat_color:
            info_parts.append(pet.coat_color)
        if pet.batch:
            info_parts.append(f"批次:{pet.batch}")
        
        selected = pet.selected_name or "-"
        candidates = ", ".join(pet.candidate_names) if pet.candidate_names else "-"
        favorites = ", ".join(pet.favorite_names) if pet.favorite_names else "-"
        
        table_data.append([
            " | ".join(info_parts),
            selected,
            favorites,
            candidates
        ])
    
    click.echo(click.style("=== 宠物名字列表 ===", fg="cyan", bold=True))
    click.echo(tabulate(
        table_data,
        headers=["宠物信息", "正式名", "收藏名", "候选名"],
        tablefmt="simple"
    ))
    click.echo()


def _add_favorite(storage, item: str):
    try:
        pet_id, name = item.split(":", 1)
    except ValueError:
        raise click.ClickException(f"格式错误: {item}，应为 pet_id:name")
    
    pet = storage.get_pet(pet_id)
    if not pet:
        pet = storage.get_pet(pet_id)
        if not pet:
            all_pets = storage.load_pets()
            for p in all_pets:
                if p.id.startswith(pet_id):
                    pet = p
                    break
    
    if not pet:
        raise click.ClickException(f"找不到宠物: {pet_id}")
    
    if name not in pet.favorite_names:
        pet.favorite_names.append(name)
        storage.update_pet(pet)
        click.echo(click.style(f"已添加 {name} 到宠物 {pet.id[:8]} 的收藏", fg="green"))
    else:
        click.echo(f"{name} 已在收藏中")


def _remove_favorite(storage, item: str):
    try:
        pet_id, name = item.split(":", 1)
    except ValueError:
        raise click.ClickException(f"格式错误: {item}，应为 pet_id:name")
    
    pet = storage.get_pet(pet_id)
    if not pet:
        all_pets = storage.load_pets()
        for p in all_pets:
            if p.id.startswith(pet_id):
                pet = p
                break
    
    if not pet:
        raise click.ClickException(f"找不到宠物: {pet_id}")
    
    if name in pet.favorite_names:
        pet.favorite_names.remove(name)
        storage.update_pet(pet)
        click.echo(click.style(f"已从宠物 {pet.id[:8]} 的收藏中移除 {name}", fg="green"))
    else:
        click.echo(f"{name} 不在收藏中")


def _set_selected_name(storage, item: str):
    try:
        pet_id, name = item.split(":", 1)
    except ValueError:
        raise click.ClickException(f"格式错误: {item}，应为 pet_id:name")
    
    pet = storage.get_pet(pet_id)
    if not pet:
        all_pets = storage.load_pets()
        for p in all_pets:
            if p.id.startswith(pet_id):
                pet = p
                break
    
    if not pet:
        raise click.ClickException(f"找不到宠物: {pet_id}")
    
    old_name = pet.selected_name
    pet.selected_name = name
    
    if name not in pet.favorite_names:
        pet.favorite_names.append(name)
    
    storage.update_pet(pet)
    
    if old_name:
        click.echo(click.style(f"已将宠物 {pet.id[:8]} 的名字从 {old_name} 改为 {name}", fg="green"))
    else:
        click.echo(click.style(f"已设置宠物 {pet.id[:8]} 的正式名为 {name}", fg="green"))
    
    stats = storage.load_stats()
    stats.named_pets = sum(1 for p in storage.load_pets() if p.selected_name)
    storage.save_stats(stats)


def _select_from_favorites(storage, pets: List[Pet]):
    for pet in pets:
        if not pet.favorite_names:
            if pet.candidate_names:
                click.echo(f"\n宠物 {pet.id[:8]} ({pet.species}) 没有收藏名，但有候选名:")
                click.echo(f"候选名: {', '.join(pet.candidate_names)}")
                if click.confirm("是否查看候选名？", default=False):
                    for i, name in enumerate(pet.candidate_names, 1):
                        click.echo(f"  {i}. {name}")
            else:
                click.echo(f"宠物 {pet.id[:8]} ({pet.species}) 没有收藏名和候选名")
            continue
        
        click.echo(click.style(f"\n宠物 {pet.id[:8]} ({pet.species})", fg="cyan", bold=True))
        click.echo(f"当前正式名: {pet.selected_name or '-'}")
        click.echo("收藏名字:")
        
        for i, name in enumerate(pet.favorite_names, 1):
            marker = " *" if name == pet.selected_name else ""
            click.echo(f"  {i}. {name}{marker}")
        
        choice = click.prompt(
            "\n选择一个名字设为正式名 (0跳过，c查看候选名)",
            type=str,
            default="0"
        )
        
        if choice == "0":
            continue
        elif choice.lower() == "c":
            if pet.candidate_names:
                click.echo("候选名:")
                for i, name in enumerate(pet.candidate_names, 1):
                    click.echo(f"  {i}. {name}")
                sub_choice = click.prompt(
                    "选择候选名编号加入收藏并设为正式名 (0跳过)",
                    type=int,
                    default=0
                )
                if sub_choice > 0 and sub_choice <= len(pet.candidate_names):
                    selected = pet.candidate_names[sub_choice - 1]
                    if selected not in pet.favorite_names:
                        pet.favorite_names.append(selected)
                    pet.selected_name = selected
                    storage.update_pet(pet)
                    click.echo(click.style(f"已设置正式名: {selected}", fg="green"))
            else:
                click.echo("没有候选名")
            continue
        
        try:
            idx = int(choice)
            if 1 <= idx <= len(pet.favorite_names):
                selected = pet.favorite_names[idx - 1]
                pet.selected_name = selected
                storage.update_pet(pet)
                click.echo(click.style(f"已设置正式名: {selected}", fg="green"))
        except ValueError:
            click.echo("输入无效，已跳过")
    
    stats = storage.load_stats()
    stats.named_pets = sum(1 for p in storage.load_pets() if p.selected_name)
    storage.save_stats(stats)
