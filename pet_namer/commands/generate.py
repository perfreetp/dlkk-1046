import click
import uuid
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
@pass_storage
def generate(storage, species, gender, age, coat_color, personality, batch,
             min_length, max_length, language, style, forbidden, count,
             exclude_used, avoid_similar, pet_id, all_pets, replay, interactive):
    """为宠物生成候选名字"""
    
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
