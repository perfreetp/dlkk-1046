import click
import sys
from .storage import Storage
from .name_library import init_name_library

pass_storage = click.make_pass_decorator(Storage)


@click.group()
@click.version_option()
@click.option("--data-dir", default=".pet-namer", help="数据存储目录")
@click.pass_context
def cli(ctx, data_dir):
    """宠物起名命令行工具 - 批量生成待领养动物名字"""
    storage = Storage(data_dir)
    init_name_library(storage)
    ctx.obj = storage


from .commands.generate import generate
from .commands.filter import filter_cmd
from .commands.import_cmd import import_cmd
from .commands.favorite import favorite
from .commands.rename import rename
from .commands.export import export
from .commands.stats import stats
from .commands.batch import batch

cli.add_command(generate)
cli.add_command(filter_cmd, name="filter")
cli.add_command(import_cmd, name="import")
cli.add_command(favorite)
cli.add_command(rename)
cli.add_command(export)
cli.add_command(stats)
cli.add_command(batch)


def main():
    try:
        cli()
    except KeyboardInterrupt:
        click.echo("\n操作已取消")
        sys.exit(0)
    except Exception as e:
        click.echo(f"\n错误: {str(e)}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
