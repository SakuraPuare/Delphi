from __future__ import annotations

import time

import httpx
import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn
from rich.table import Table

app = typer.Typer(name="delphi", help="Delphi - 可离线部署的本地知识库系统")
console = Console()
err_console = Console(stderr=True)

# Global state
_state: dict = {"api_url": "http://localhost:8888", "verbose": False}


@app.callback()
def main(
    api_url: str = typer.Option("http://localhost:8888", help="API Server 地址"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="输出详细日志"),
) -> None:
    _state["api_url"] = api_url.rstrip("/")
    _state["verbose"] = verbose


def _client() -> httpx.Client:
    return httpx.Client(base_url=_state["api_url"], timeout=30)


def _handle_connection_error() -> None:
    err_console.print(f"[red]无法连接到 API Server ({_state['api_url']})[/red]")
    err_console.print("请确认服务已启动: delphi serve")
    raise SystemExit(2)


def _handle_http_error(resp: httpx.Response) -> None:
    try:
        detail = resp.json().get("detail", resp.text)
    except Exception:
        detail = resp.text
    err_console.print(f"[red]请求失败 ({resp.status_code}): {detail}[/red]")
    raise SystemExit(1)


# --- serve ---


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="监听地址"),
    port: int = typer.Option(8888, help="监听端口"),
    reload: bool = typer.Option(False, help="开发模式热重载"),
) -> None:
    """启动 API 服务"""
    import uvicorn

    uvicorn.run("delphi.api.app:app", host=host, port=port, reload=reload)


# --- status ---


@app.command()
def status() -> None:
    """查看系统状态"""
    try:
        with _client() as c:
            resp = c.get("/status")
    except httpx.ConnectError:
        _handle_connection_error()

    if resp.status_code != 200:
        _handle_http_error(resp)

    data = resp.json()
    console.print("\n[bold]服务状态[/bold]")
    for name, info in data.items():
        ok = info.get("ok", False)
        mark = "[green]✓[/green]" if ok else "[red]✗[/red]"
        extra_parts: list[str] = []
        if info.get("model"):
            extra_parts.append(f"模型: {info['model']}")
        if info.get("collections") is not None:
            extra_parts.append(f"集合数: {info['collections']}")
        if info.get("error") and not ok:
            extra_parts.append(f"错误: {info['error']}")
        extra = "  " + ", ".join(extra_parts) if extra_parts else ""
        console.print(f"  {name:<14} {mark}{extra}")
    console.print()


# --- import ---

import_app = typer.Typer(help="数据导入")
app.add_typer(import_app, name="import")


def _poll_task(client: httpx.Client, task_id: str) -> None:
    """Poll a task until completion, showing a progress bar."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        bar = progress.add_task("导入中...", total=None)
        while True:
            resp = client.get(f"/import/tasks/{task_id}")
            if resp.status_code != 200:
                _handle_http_error(resp)
            info = resp.json()
            total = info.get("total", 0)
            processed = info.get("processed", 0)
            status = info.get("status", "pending")

            if total > 0:
                progress.update(bar, total=total, completed=processed)

            if status == "done":
                progress.update(bar, total=total, completed=total)
                break
            if status == "failed":
                err_console.print(f"[red]导入失败: {info.get('error', '未知错误')}[/red]")
                raise SystemExit(1)

            time.sleep(2)

    console.print(f"[green]✓ 导入完成: {info.get('processed', 0)} 个文件已处理[/green]")


@import_app.command("git")
def import_git(
    url: str = typer.Argument(help="Git 仓库 URL 或本地路径"),
    project: str = typer.Option("", help="目标项目名称"),
    branch: str = typer.Option("main", help="指定分支"),
    include: list[str] | None = typer.Option(None, help="文件过滤 glob"),  # noqa: B008
    exclude: list[str] | None = typer.Option(None, help="排除文件 glob"),  # noqa: B008
    depth: int = typer.Option(1, help="clone 深度"),
) -> None:
    """导入 Git 仓库"""
    body = {
        "url": url,
        "project": project,
        "branch": branch,
        "include": include or [],
        "exclude": exclude or [],
        "depth": depth,
    }
    try:
        with _client() as c:
            resp = c.post("/import/git", json=body)
            if resp.status_code not in (200, 201, 202):
                _handle_http_error(resp)
            task_id = resp.json()["task_id"]
            console.print(f"任务已创建: {task_id}")
            _poll_task(c, task_id)
    except httpx.ConnectError:
        _handle_connection_error()


@import_app.command("docs")
def import_docs(
    path: str = typer.Argument(help="文档目录路径"),
    project: str = typer.Option("", help="目标项目名称"),
    recursive: bool = typer.Option(True, "--recursive", "-r", help="递归扫描子目录"),
    type_: list[str] | None = typer.Option(None, "--type", help="文件类型过滤"),  # noqa: B008
) -> None:
    """导入文档目录"""
    body = {
        "path": path,
        "project": project,
        "recursive": recursive,
        "file_types": type_ or ["md", "txt", "pdf", "html"],
    }
    try:
        with _client() as c:
            resp = c.post("/import/docs", json=body)
            if resp.status_code not in (200, 201, 202):
                _handle_http_error(resp)
            task_id = resp.json()["task_id"]
            console.print(f"任务已创建: {task_id}")
            _poll_task(c, task_id)
    except httpx.ConnectError:
        _handle_connection_error()


@import_app.command("media")
def import_media(
    path: str = typer.Argument(help="音视频目录路径"),
    project: str = typer.Option("", help="目标项目名称"),
    recursive: bool = typer.Option(True, "--recursive", "-r", help="递归扫描子目录"),
    whisper_model: str = typer.Option("large-v3", "--model", help="Whisper 模型大小"),
) -> None:
    """导入音视频文件（转录后入库）"""
    body = {
        "path": path,
        "project": project,
        "recursive": recursive,
        "whisper_model": whisper_model,
    }
    try:
        with _client() as c:
            resp = c.post("/import/media", json=body)
            if resp.status_code not in (200, 201, 202):
                _handle_http_error(resp)
            task_id = resp.json()["task_id"]
            console.print(f"任务已创建: {task_id}")
            _poll_task(c, task_id)
    except httpx.ConnectError:
        _handle_connection_error()


# --- query ---


@app.command()
def query(
    question: str = typer.Argument(help="查询问题"),
    project: str = typer.Option("", help="指定查询的项目"),
    top_k: int = typer.Option(5, help="召回文档数量"),
    stream: bool = typer.Option(False, "--stream/--no-stream", help="流式输出"),
    show_sources: bool = typer.Option(False, "--show-sources", help="显示引用来源"),
) -> None:
    """查询知识库"""
    body = {"question": question, "project": project, "top_k": top_k}
    try:
        with _client() as c:
            if stream:
                with c.stream("POST", "/query/stream", json=body) as resp:
                    if resp.status_code != 200:
                        resp.read()
                        _handle_http_error(resp)
                    for line in resp.iter_lines():
                        if line.startswith("data: "):
                            token = line[6:]
                            console.print(token, end="")
                console.print()
            else:
                resp = c.post("/query", json=body)
                if resp.status_code != 200:
                    _handle_http_error(resp)
                data = resp.json()
                console.print(data["answer"])
                if show_sources and data.get("sources"):
                    console.print("\n[bold]来源:[/bold]")
                    for i, src in enumerate(data["sources"], 1):
                        score = src.get("score", 0)
                        console.print(f"  [{i}] {src['file']} (相关度 {score:.2f})")
    except httpx.ConnectError:
        _handle_connection_error()


# --- projects ---

projects_app = typer.Typer(help="项目管理")
app.add_typer(projects_app, name="projects")


@projects_app.command("list")
def projects_list() -> None:
    """列出所有项目"""
    try:
        with _client() as c:
            resp = c.get("/projects")
    except httpx.ConnectError:
        _handle_connection_error()

    if resp.status_code != 200:
        _handle_http_error(resp)

    projects = resp.json()
    if not projects:
        console.print("暂无项目")
        return

    table = Table(title="项目列表")
    table.add_column("名称", style="cyan")
    table.add_column("文档块数", justify="right")
    table.add_column("创建时间")
    for p in projects:
        table.add_row(p["name"], str(p.get("chunk_count", 0)), p.get("created_at", ""))
    console.print(table)


@projects_app.command("create")
def projects_create(
    name: str = typer.Argument(help="项目名称"),
    description: str = typer.Option("", help="项目描述"),
) -> None:
    """创建项目"""
    try:
        with _client() as c:
            resp = c.post("/projects", json={"name": name, "description": description})
    except httpx.ConnectError:
        _handle_connection_error()

    if resp.status_code not in (200, 201):
        _handle_http_error(resp)

    console.print(f"[green]✓ 项目 '{name}' 已创建[/green]")


@projects_app.command("delete")
def projects_delete(
    name: str = typer.Argument(help="项目名称"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
) -> None:
    """删除项目"""
    if not yes:
        confirm = typer.confirm(f"确认删除项目 '{name}'？此操作不可恢复")
        if not confirm:
            raise typer.Abort()

    try:
        with _client() as c:
            resp = c.delete(f"/projects/{name}")
    except httpx.ConnectError:
        _handle_connection_error()

    if resp.status_code not in (200, 204):
        _handle_http_error(resp)

    console.print(f"[green]✓ 项目 '{name}' 已删除[/green]")


if __name__ == "__main__":
    app()
