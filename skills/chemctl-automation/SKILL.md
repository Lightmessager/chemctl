---
name: chemctl-automation
description: "Use when the user wants to use chemctl for computational chemistry automation: ORCA/Gaussian input preparation, PBS submission, job monitoring, SFTP result synchronization, output parsing, or retrieving energies, structures, frequencies, mixed basis sets and ECP information. Also applies to Chinese requests for chemctl 自动计算、提交任务、解析服务器输出。"
---

# chemctl 计算化学自动化

使用已安装的 chemctl CLI / 本地 API 执行用户要求的流程，优先复用现有配置和结果。不要把使用软件变成重新开发软件。默认少测试，不为了验证技能额外提交计算。

## 定位与连接

1. 如果本技能旁的 `references/local-environment.md` 存在，读取它作为本机定位提示；这是环境记录，不是永久计算授权。可分享版本不包含此文件。
2. 其余环境优先读取 `CHEMCTL_PROJECT`，其次在当前工作区定位 `pyproject.toml` 和 `src/chemctl`。不能定位时才询问安装目录。Windows 使用项目 `.venv/Scripts/python.exe`，不要误用系统 Python。
3. 先调用 health，核对 home、parser_version、capabilities。现有 API 可用就复用，不重启、不关闭 GUI。API 不可用时用项目环境启动后台 `python -m chemctl serve`，设置正确的 `CHEMCTL_HOME`，Windows 后台进程隐藏窗口。启动后确认 health；已有其他服务占用端口时不要杀进程。
4. 列出服务器并选用户指定的记录；只有一个真实服务器时可沿用它并说明。不要把 demo 模拟服务器当成计算服务器。已存私钥会自动重连，不要读取或展示私钥内容。认证失败时让用户在 GUI 完成登录，不让用户把密码发到聊天里。

命令、API 参数及完整提交示例见 [references/interface.md](references/interface.md)。仅在准备新计算脚本时读 [references/calculation.md](references/calculation.md)。

## 先确定本次目标

- 解析已有文件：只下载/读取用户指定范围的输出，不提交新计算。
- 新计算：优先使用用户已有输入和提交脚本。核对几何、总电荷、多重度、方法、基组/逐元素基组与 ECP、溶剂、计算类型及资源。会改变科学问题的缺失项要询问；可从输入、原始输出、配置推导的内容不重复问。
- 用户已经要求执行计算且范围与资源明确时，完成预览后直接执行，不要求重复确认。授权只覆盖本次目标；仅请求解析或预览不授权提交。不要擅自启动批量扫描、无限优化重试或更换科学方法。

## 提交 → 监控 → 同步 → 解析

1. 使用独立本地任务目录，只放本次所需文件。真实提交会上传整个输入目录，不能把项目根目录、密钥或其他研究数据作为输入目录。
2. 确认 PBS 探测证据及真正的计算程序路径。`orca` 可能是同名屏幕阅读器；不能仅凭 command-v 判断。软件探测只读，不能用 `qsub -help` / `qsub --version` 探测调度器。
3. 用固定幂等键 dry-run，核对完整脚本、资源、上传清单、远程目录。API 提交携带同一计划的 `expected_plan_hash`；记录 job_id、remote_job_id、幂等键、输入目录和计划摘要到本次本地任务记录，便于会话恢复。
4. 实际提交一次。网络超时或 `submission_unknown` 时先按 job_id 刷新、检查回执和 events；不要换键再次 qsub。`unknown` 不是成功，`qstat` 查不到也不是成功。无法消除提交歧义时停止自动重提并报告现有证据。
5. 按约 30 秒刷新任务；排队期间只报告有意义的变化。`job wait --timeout` 是观察期限，不会取消任务。用户要求跟到完成时继续在当前会话监控；停止等待、取消和完成是不同操作。
6. 完成后调用 sync；调用返回 queued 不代表已下载。等待 `sync_status=succeeded`，随后查询 `parse_batch_id`，确认批次结束和失败计数，再按 **job** 参数查询关联计算。失败任务可同步日志诊断，但不得报告科学成功。
7. 查看 calculation 详情和 warnings，按需要读取结构、频率、能量。列表接口不包含全部字段；列表分页与结构分页应检查 total。

## 解释结果

- 同时说明调度器状态、程序终止证据和解析状态。`parsed`、`completed`、几何收敛、无虚频不是同一概念。
- 能量单位 Eh，坐标 Å，频率 cm⁻¹。最终电子能量不等于自由能；不同电荷、组成、方法、基组或溶剂的数值不要直接当作可比较能差。
- 当前 Gaussian 能量主要来自 SCF 标记；即使方法识别成 MP2/CC，也不要把 SCF 能量冒称其最终相关能量。复杂多阶段、ONIOM、IRC/TS 语义仍需检查原文。
- Gaussian 混合基组查看 `basis_groups` 的元素和中心编号，ECP 查看 `ecp_centers`。不要按“重原子”阈值猜测 SDD，不把 SDD 轨道基组等同于已使用 ECP。`custom (explicit shells)` 不能擅自重命名。
- 文件名含 TS 或 F 不证明过渡态或频率计算；单个虚频也需结合振动模式与目标反应判断。

## 结果交付与清理

给出任务/计算 ID、实际方法与分元素基组、溶剂、终止/解析状态、主要数值、可打开的本地结果路径和限制。对已有输出保留远程来源路径。不要把真实数据或服务器信息推送到公开仓库。

只有本次指令授权清理时才删除文件。核对任务已停止、精确独立目录与归属，保存用户需要的结果后只清理授权范围；不递归删除共享 scratch、登录目录或其他任务目录。程序当前没有通用删除 API，不能发明 cleanup 路由。清理完成要验证并报告；生产结果默认保留。
