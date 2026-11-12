# chemctl 接口与执行方法

以下与 chemctl 0.1 / parser 0.1.4 对齐。先看 health；版本有变化时用 CLI `--help` 或本地 `/openapi.json` 核对，不凭文档猜新增接口。

## CLI（Windows PowerShell）

在项目目录运行；项目目录来自环境定位，不硬编码用户机器。

```powershell
$chem = '.\.venv\Scripts\chemctl.exe'
& $chem system health
& $chem server list
& $chem server test myserver
& $chem server software myserver
& $chem job list --server myserver
& $chem job status job_... --refresh
& $chem job sync job_...
& $chem parse batch --source .\outputs --recursive
& $chem parse status batch_...
& $chem data query --job job_...
& $chem data structures calc_... --stage final --format xyz
& $chem data frequencies calc_... --imaginary-only
```

CLI 默认 JSON envelope：`ok/data/error/meta`。API 错误/非零退出不能忽略。PowerShell 写 JSON 用 ConvertTo-Json 或脚本结构化序列化，不把含引号输入拼进 shell 命令。

服务不可用且确认没有正确运行实例时，可用项目 Python 隐藏启动 `-m chemctl serve`，工作目录设项目根，`CHEMCTL_HOME=<project>/.chemctl`；若已有非默认 home，沿用它。`CHEMCTL_URL` 默认 http://127.0.0.1:8765。不要盲目改变已运行 API 的数据目录。

## Python Client / API

从项目虚拟环境调用，避免自己处理密码/HTTP envelope：

```python
from chemctl.client import Client
c = Client()  # 使用 CHEMCTL_URL，自动添加 /api/v1
health = c.get('/health')['data']
servers = c.get('/servers')['data']['items']
```

常用接口：

| 方法与路径（Client 不写 /api/v1） | 关键参数 / 返回值 |
|---|---|
| GET /servers | items；已有 SSH 配置及 last_probe |
| POST /servers/{server}/test | 不带 password 使用保存密钥；返回探测证据 |
| POST /servers/{server}/software | 只读 PATH/模块/常见安装目录探测；候选不等于已验证软件 |
| POST /servers/{server}/enable-key | 需要已有会话；改变 authorized_keys，只有用户要求配置免密时调用 |
| POST /jobs | server_id,input_path,script,engine,profile,tag,idempotency_key,dry_run,expected_plan_hash |
| GET /jobs | server/status/limit/offset；用于恢复已有任务 |
| GET /jobs/{job_id} | 本地缓存状态；不会主动查队列 |
| POST /jobs/{job_id}/refresh | 查真实队列/退出记录 |
| GET /jobs/{job_id}/events | 审计事件 |
| POST /jobs/{job_id}/sync | parse=true 默认；后台同步，随后检查任务 sync_status |
| POST /jobs/{job_id}/cancel | 显式取消已授权任务；CLI 对应 job cancel --yes |
| POST /parse/batches | source,recursive,force；后台任务，返回 parse_batch_id |
| GET /parse/batches/{id} | status,total,processed,failed,errors |
| GET /files | 分页文件记录，用 local_path 确认导入文件对应的 calculation_id |
| GET /calculations | **job**（不是 job_id）,engine,status,select,limit,offset |
| GET /calculations/{id} | method,basis_set,basis_groups,ecp_centers,solvent_name,solvent_model,convergence,warnings 等 |
| GET /calculations/{id}/structures | stage=all/initial/final，limit/offset；final 需有正常终止证据 |
| GET /calculations/{id}/energies | 分页观测能量与来源；不要用步骤号推断与结构一一对应 |
| GET /calculations/{id}/frequencies | imaginary_only=true 可筛负频率 |

实际提交的惯用调用（仅在用户授权的计算范围内执行；目录、脚本、引擎应先验证）：

```python
from pathlib import Path
from chemctl.client import Client
c = Client()
payload = dict(server_id=server_id, input_path=str(Path(input_dir).resolve()),
               script=script_name, engine=engine, profile='default',
               tag=task_label, idempotency_key=stable_request_key)
plan = c.post('/jobs', **payload, dry_run=True)['data']
# 保存 plan，并检查 script_text/resources/input_manifest/remote_directory。
job = c.post('/jobs', **payload, expected_plan_hash=plan['plan_hash'])['data']
```

上述 server_id 等变量来自本次任务；不能原样使用省略符或为重试生成新键。引擎枚举为 `orca` / `gaussian09d`，只是标签，真正执行由脚本决定。当前 profile 不自动生成计算输入。

## 读取服务器已有输出

没有通用远程文件浏览 API；`file fetch` 只导出已索引本地文件，不能用来下载任意远程路径。确需读取用户授权目录时，可在项目 Python 中使用现有 SSH 适配器，复用配置与保存密钥：

```python
from chemctl.adapters import open_ssh
server = next(s for s in c.get('/servers')['data']['items'] if s['server_id'] == server_id)
ssh = open_ssh(server)
try:
    with ssh.open_sftp() as sftp:
        # remote_file 与 local_file 均已确定；使用独立本地导入目录。
        before = sftp.stat(remote_file)
        sftp.get(remote_file, str(local_file))
        after = sftp.stat(remote_file)
        if (before.st_size, before.st_mtime) != (after.st_size, after.st_mtime):
            raise RuntimeError('Remote output changed during download; do not claim a final result')
finally:
    ssh.close()
batch = c.post('/parse/batches', source=str(local_file), recursive=False)['data']
```

本地目录先创建，避免覆盖已有导入副本，并保留服务器 ID、远程路径、大小/mtime 的来源记录。此适配器不能获取后台内存中的密码会话；无已存私钥时请用户配置免密或通过常用客户端下载文件，不索取聊天密码。
