import click
from tabulate import tabulate
from datetime import datetime

from ..models import ReviewEntry, BatchTaskRecord
from ..cli import pass_storage


STATUS_COLORS = {
    "pending": "yellow",
    "accepted": "green",
    "modified": "blue",
    "rejected": "red",
}

STATUS_LABELS = {
    "pending": "待审核",
    "accepted": "已接受",
    "modified": "已修改",
    "rejected": "已拒绝",
}

SPECIES_CN = {
    "cat": "猫咪",
    "dog": "狗狗",
    "rabbit": "兔子",
}

GENDER_CN = {
    "male": "公",
    "female": "母",
    "neutral": "中性",
}


@click.command()
@click.argument("task_id")
@click.option("--accept-all", is_flag=True, help="一次性接受所有待审核宠物的推荐名")
@click.option("--reject", "-r", multiple=True, help="拒绝/退回某宠物ID，可重复")
@click.option("--accept", "-a", multiple=True, help="接受某宠物ID的推荐名，可重复")
@click.option("--change", "-c", multiple=True, help="改用某候选名，格式 pet_id:新名字，可重复")
@click.option("--note", "-n", multiple=True, help="添加备注，格式 pet_id:备注内容，可重复")
@click.option("--status", type=click.Choice(["pending_review", "review_in_progress", "reviewed"]),
              default=None, help="切换任务审核阶段状态")
@click.option("--finalize", is_flag=True, help="结束审核：把所有accepted/modified的名字写入宠物正式名，任务标记为reviewed")
@pass_storage
def review(storage, task_id, accept_all, reject, accept, change, note, status, finalize):
    """审核批量任务的推荐名字单

    用法示例：
      pet-namer review abc123                   # 查看任务审核状态
      pet-namer review abc123 --accept pet1 --accept pet2
      pet-namer review abc123 --change pet3:Lucky
      pet-namer review abc123 --reject pet4
      pet-namer review abc123 --accept-all      # 全部接受
      pet-namer review abc123 --finalize        # 结束审核并写入正式名
    """

    task = storage.get_task(task_id)
    if not task:
        raise click.ClickException(f"找不到任务: {task_id}")

    if not task.reviews:
        click.echo(click.style("该任务暂无待审核名单", fg="yellow"))
        click.echo("请先用 batch 命令生成推荐名后再进行审核")
        return

    pets = storage.load_pets()
    pet_by_id = {p.id: p for p in pets}

    _show_review_table(task, pet_by_id)

    if status is not None:
        task.status = status
        click.echo(click.style(f"\n任务状态已更新为: {status}", fg="cyan"))

    now = datetime.now().isoformat()

    if accept_all:
        count = 0
        for rev in task.reviews:
            if rev.status == "pending":
                rev.status = "accepted"
                rev.final_name = rev.recommended_name
                rev.reviewed_at = now
                count += 1
        click.echo(click.style(f"\n已接受全部 {count} 只待审核宠物的推荐名", fg="green"))

    def _find_review(pid: str) -> ReviewEntry:
        for rev in task.reviews:
            if rev.pet_id == pid or rev.pet_id.startswith(pid):
                return rev
        return None

    for pid in accept:
        rev = _find_review(pid)
        if not rev:
            click.echo(click.style(f"警告: 找不到宠物ID {pid}，已跳过", fg="yellow"))
            continue
        rev.status = "accepted"
        rev.final_name = rev.recommended_name
        rev.reviewed_at = now
        click.echo(click.style(f"已接受 {rev.pet_id[:8]} 的推荐名: {rev.recommended_name}", fg="green"))

    for pid in reject:
        rev = _find_review(pid)
        if not rev:
            click.echo(click.style(f"警告: 找不到宠物ID {pid}，已跳过", fg="yellow"))
            continue
        rev.status = "rejected"
        rev.final_name = None
        rev.reviewed_at = now
        click.echo(click.style(f"已拒绝 {rev.pet_id[:8]} 的推荐名", fg="red"))

    for item in change:
        if ":" not in item:
            click.echo(click.style(f"警告: 格式错误 {item}，应为 pet_id:新名字，已跳过", fg="yellow"))
            continue
        pid, new_name = item.split(":", 1)
        rev = _find_review(pid)
        if not rev:
            click.echo(click.style(f"警告: 找不到宠物ID {pid}，已跳过", fg="yellow"))
            continue
        rev.status = "modified"
        rev.final_name = new_name
        rev.reviewed_at = now
        click.echo(click.style(f"已将 {rev.pet_id[:8]} 的名字改为: {new_name}", fg="blue"))

    for item in note:
        if ":" not in item:
            click.echo(click.style(f"警告: 格式错误 {item}，应为 pet_id:备注内容，已跳过", fg="yellow"))
            continue
        pid, note_text = item.split(":", 1)
        rev = _find_review(pid)
        if not rev:
            click.echo(click.style(f"警告: 找不到宠物ID {pid}，已跳过", fg="yellow"))
            continue
        rev.note = note_text
        click.echo(click.style(f"已为 {rev.pet_id[:8]} 添加备注", fg="cyan"))

    if finalize:
        pending_count = sum(1 for rev in task.reviews if rev.status == "pending")
        if pending_count > 0:
            click.echo(click.style(f"\n仍有 {pending_count} 只宠物处于待审核状态", fg="yellow"))
            if not click.confirm("是否继续结束审核？未审核的宠物将不会写入正式名", default=False):
                click.echo("已取消结束审核")
            else:
                _finalize_task(storage, task, pet_by_id)
        else:
            _finalize_task(storage, task, pet_by_id)

    storage.update_task(task)

    click.echo()
    _show_review_table(task, pet_by_id, title="最终审核状态")


def _show_review_table(task: BatchTaskRecord, pet_by_id: dict, title: str = "当前审核状态"):
    click.echo(click.style(f"=== {title} (任务: {task.id}) ===", fg="cyan", bold=True))
    click.echo(f"任务状态: {task.status}")
    click.echo()

    table_data = []
    for i, rev in enumerate(task.reviews, 1):
        pet = pet_by_id.get(rev.pet_id)
        pet_id_short = rev.pet_id[:8]
        species = SPECIES_CN.get(pet.species, pet.species) if pet and pet.species else "-"
        gender = GENDER_CN.get(pet.gender, pet.gender) if pet and pet.gender else "-"
        coat_color = pet.coat_color if pet and pet.coat_color else "-"
        recommended = rev.recommended_name or "-"
        final = rev.final_name or "-"
        status_label = STATUS_LABELS.get(rev.status, rev.status)
        status_color = STATUS_COLORS.get(rev.status)
        status_display = click.style(status_label, fg=status_color) if status_color else status_label
        note_text = rev.note or "-"

        table_data.append([
            i,
            pet_id_short,
            species,
            gender,
            coat_color,
            recommended,
            final,
            status_display,
            note_text,
        ])

    click.echo(tabulate(
        table_data,
        headers=["#", "宠物ID", "物种", "性别", "毛色", "推荐名", "最终名", "状态", "备注"],
        tablefmt="simple"
    ))

    total = len(task.reviews)
    pending = sum(1 for r in task.reviews if r.status == "pending")
    accepted = sum(1 for r in task.reviews if r.status == "accepted")
    modified = sum(1 for r in task.reviews if r.status == "modified")
    rejected = sum(1 for r in task.reviews if r.status == "rejected")

    click.echo()
    stats_table = [
        ["总数", total],
        [click.style("待审核", fg="yellow"), pending],
        [click.style("已接受", fg="green"), accepted],
        [click.style("已修改", fg="blue"), modified],
        [click.style("已拒绝", fg="red"), rejected],
    ]
    click.echo(tabulate(stats_table, tablefmt="simple"))


def _finalize_task(storage, task: BatchTaskRecord, pet_by_id: dict):
    written = 0
    for rev in task.reviews:
        if rev.status in ("accepted", "modified") and rev.final_name:
            pet = pet_by_id.get(rev.pet_id)
            if pet:
                pet.selected_name = rev.final_name
                storage.update_pet(pet)
                written += 1

    task.status = "reviewed"
    click.echo()
    click.echo(click.style(f"✅ 审核完成，已为 {written} 只宠物写入正式名", fg="green", bold=True))
