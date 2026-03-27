import typer

app = typer.Typer(name="delphi", help="Delphi - 可离线部署的本地知识库系统")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="监听地址"),
    port: int = typer.Option(8888, help="监听端口"),
    reload: bool = typer.Option(False, help="开发模式热重载"),
) -> None:
    """启动 API 服务"""
    import uvicorn

    uvicorn.run("delphi.api.app:app", host=host, port=port, reload=reload)


@app.command()
def status() -> None:
    """查看系统状态"""
    typer.echo("TODO: 查询 API Server 状态")


import_app = typer.Typer(help="数据导入")
app.add_typer(import_app, name="import")


@import_app.command("git")
def import_git(
    url: str = typer.Argument(help="Git 仓库 URL 或本地路径"),
    project: str = typer.Option("", help="目标项目名称"),
) -> None:
    """导入 Git 仓库"""
    typer.echo(f"TODO: 导入 Git 仓库 {url}")


@import_app.command("docs")
def import_docs(
    path: str = typer.Argument(help="文档目录路径"),
    project: str = typer.Option("", help="目标项目名称"),
) -> None:
    """导入文档目录"""
    typer.echo(f"TODO: 导入文档目录 {path}")


projects_app = typer.Typer(help="项目管理")
app.add_typer(projects_app, name="projects")


@projects_app.command("list")
def projects_list() -> None:
    """列出所有项目"""
    typer.echo("TODO: 列出项目")


@projects_app.command("create")
def projects_create(name: str = typer.Argument(help="项目名称")) -> None:
    """创建项目"""
    typer.echo(f"TODO: 创建项目 {name}")


@projects_app.command("delete")
def projects_delete(name: str = typer.Argument(help="项目名称")) -> None:
    """删除项目"""
    typer.echo(f"TODO: 删除项目 {name}")


if __name__ == "__main__":
    app()
