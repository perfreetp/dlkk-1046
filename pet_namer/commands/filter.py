import click
from tabulate import tabulate

from ..generator import NameGenerator
from ..cli import pass_storage


@click.command("filter")
@click.option("--threshold", type=float, default=0.85, help="发音相似度阈值 (0-1)")
@click.option("--check-selected/--no-check-selected", default=True, help="检查已选中的名字")
@click.option("--check-candidates/--no-check-candidates", default=True, help="检查候选名字")
@click.option("--check-favorites/--no-check-favorites", default=True, help="检查收藏名字")
@click.option("--fix-duplicates/--no-fix-duplicates", default=False, help="自动修复重复名字")
@click.option("--fix-similar/--no-fix-similar", default=False, help="自动标记发音相近名字")
@click.option("--batch", help="指定批次筛选")
@pass_storage
def filter_cmd(storage, threshold, check_selected, check_candidates, check_favorites,
               fix_duplicates, fix_similar, batch):
    """检查重复名和发音相近名"""
    
    pets = storage.load_pets()
    
    if batch:
        pets = [p for p in pets if p.batch == batch]
    
    if not pets:
        raise click.ClickException("没有找到宠物数据")
    
    name_library = storage.load_names()
    generator = NameGenerator(name_library)
    
    all_names = []
    name_pet_map = {}
    
    for pet in pets:
        pet_label = f"{pet.id[:8]}"
        
        if check_selected and pet.selected_name:
            all_names.append(pet.selected_name)
            name_pet_map.setdefault(pet.selected_name, []).append(
                (pet_label, "selected")
            )
        
        if check_candidates:
            for name in pet.candidate_names:
                all_names.append(name)
                name_pet_map.setdefault(name, []).append(
                    (pet_label, "candidate")
                )
        
        if check_favorites:
            for name in pet.favorite_names:
                all_names.append(name)
                name_pet_map.setdefault(name, []).append(
                    (pet_label, "favorite")
                )
    
    click.echo(click.style("\n=== 重复名检查 ===", fg="cyan", bold=True))
    duplicates = generator.find_duplicates(all_names)
    
    if duplicates:
        table_data = []
        for name_lower, variants in duplicates.items():
            unique_variants = list(set(variants))
            pets_using = []
            for variant in unique_variants:
                for pet_label, ntype in name_pet_map.get(variant, []):
                    pets_using.append(f"{pet_label}({ntype})")
            table_data.append([
                ", ".join(unique_variants),
                len(unique_variants),
                ", ".join(pets_using)
            ])
        
        click.echo(tabulate(table_data, headers=["重复名字", "次数", "使用位置"], tablefmt="simple"))
        
        if fix_duplicates:
            click.echo("\n正在修复重复名字...")
            _fix_duplicates(storage, pets, duplicates)
    else:
        click.echo("未发现重复名字 ✅")
    
    click.echo(click.style("\n=== 发音相近名字检查 ===", fg="cyan", bold=True))
    
    unique_names = list(set(all_names))
    similar_pairs = generator.find_similar(unique_names, threshold)
    
    if similar_pairs:
        table_data = []
        for name1, name2, similarity in similar_pairs:
            pets1 = ", ".join([f"{p}({t})" for p, t in name_pet_map.get(name1, [])])
            pets2 = ", ".join([f"{p}({t})" for p, t in name_pet_map.get(name2, [])])
            table_data.append([
                name1,
                name2,
                f"{similarity:.2f}",
                pets1,
                pets2
            ])
        
        click.echo(tabulate(table_data, headers=["名字1", "名字2", "相似度", "使用位置1", "使用位置2"], tablefmt="simple"))
        
        if fix_similar:
            click.echo("\n已标记发音相近名字，请人工确认后使用 rename 命令修改")
    else:
        click.echo("未发现发音相近的名字 ✅")
    
    click.echo()


def _fix_duplicates(storage, pets, duplicates):
    changed = 0
    
    for name_lower, variants in duplicates.items():
        unique_variants = list(set(variants))
        if len(unique_variants) <= 1:
            continue
        
        keep_name = unique_variants[0]
        
        for pet in pets:
            modified = False
            
            if pet.selected_name and pet.selected_name.lower() == name_lower:
                if pet.selected_name != keep_name:
                    pet.selected_name = keep_name
                    modified = True
            
            pet.candidate_names = [
                keep_name if n.lower() == name_lower and n != keep_name else n
                for n in pet.candidate_names
            ]
            if any(n.lower() == name_lower and n != keep_name for n in pet.favorite_names):
                modified = True
            
            pet.favorite_names = [
                keep_name if n.lower() == name_lower and n != keep_name else n
                for n in pet.favorite_names
            ]
            if any(n.lower() == name_lower and n != keep_name for n in pet.candidate_names):
                modified = True
            
            if modified:
                storage.update_pet(pet)
                changed += 1
    
    click.echo(f"已修复 {changed} 处重复名字，统一为规范形式")
