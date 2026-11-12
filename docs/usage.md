# 使用说明

## 本地解析

Parser 页选择 `.out` / `.log` 文件或目录并开始解析；Results 查看方法、基组、溶剂及来源。基组分组保留原子编号，避免同一元素使用不同基组时混淆。ECP 表显示中心、元素及被替代的核心电子数。更新解析器后重新解析即可刷新旧记录。

`examples` 中只有合成片段，可能被 cclib 标为 partial；真实数据请自行导入。

## SSH 与 PBS

Servers 配置主机或 SSH 别名、账号、端口、远程根目录及调度器。未知主机密钥会被拒绝，应先通过常用 SSH 客户端确认指纹并加入 known_hosts。不支持 ProxyJump/ProxyCommand。

密码仅用于本次认证，不保存。Windows 上点击“启用免密登录”会生成 RSA 3072 专用密钥，追加公钥到账号 authorized_keys，私钥以当前 Windows 用户 DPAPI 加密保存于运行目录 keys 下，并验证新连接。换电脑或 Windows 账号需重新配置。已有公钥不删除。

真实提交只支持探测确认的 PBS 家族。选择仅包含本次任务输入的目录与 Bash/sh PBS 脚本；预览显示脚本、资源及远程目录。计算程序路径、队列和资源由用户脚本明确设置。脚本支持常用 -e/-u/-l/-x shebang 选项。首次可用 --dry-run 查看计划。

提交意图与回执用于避免重复 qsub。submission_unknown 时先刷新恢复，不要更换幂等键盲目重提。qstat 无记录时查询任务退出标记，缺少证据显示 unknown。退出 0 只表示脚本成功。取消必须显式执行。

监控每 30 秒轮询最近 200 个真实任务。同步只读取该任务目录，跳过符号链接，按大小/mtime 跳过未变文件，写入本地缓存后解析。scratch 中的结果需要脚本复制回任务目录。软件不自动清理远程目录。

## CLI

```powershell
$chem = '.\.venv\Scripts\chemctl.exe'
& $chem server software myserver
& $chem job status job_... --refresh
& $chem job sync job_...
& $chem data query --job job_...
```

默认 API 为单用户本机服务，不要直接暴露到公网。项目运行目录 `.chemctl`、密钥和真实输入输出均应留在本机，不纳入公开版本库。
