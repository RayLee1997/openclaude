---
description: rsync 同步文件到 CentOS 收件箱 - 将用户指定的文件/文件夹推送到 CentOS 工作空间
---

# rsync 同步到 CentOS 工作流

// turbo-all

## 环境信息

- **CentOS**: `192.168.2.154`, 用户 `lenovo`
- **目标目录**: `/home/lenovo/Workspaces/00_Inbox/01_Rsync/`
- **模式**: 推送（只增不删，不会删除 CentOS 端已有文件）

## 使用方式

用户通过 `/rsync-lenovo` 触发，并在消息中指定需要同步的文件或文件夹路径（支持 @mention 或直接路径），例如：

- `/rsync-lenovo @[/path/to/file.pdf]`
- `/rsync-lenovo /path/to/folder/ /path/to/another-file.md`
- `/rsync-lenovo @[file1.pdf] @[folder1/]`

## 1. 解析用户输入

从用户消息中提取所有需要同步的**文件和文件夹绝对路径**列表。如果用户通过 @mention 引用了文件/文件夹，使用附带的元数据中的绝对路径。

如果没有指定任何文件或路径无效，终止工作流并提示用户提供有效路径。

## 2. 连通性检查

```bash
ssh -o ConnectTimeout=5 lenovo@192.168.2.154 "echo '✅ SSH OK' && ls -ld /home/lenovo/Workspaces/00_Inbox/01_Rsync/ 2>/dev/null || mkdir -p /home/lenovo/Workspaces/00_Inbox/01_Rsync && echo '📁 目标目录已创建'"
```

如果连接失败，终止工作流并告知用户检查 CentOS 是否在线。

## 3. 确认源文件存在

对每个路径执行 `ls` 确认文件/文件夹存在。如果任何路径不存在，终止并告知用户。

## 4. 预览同步（Dry Run）

对每个文件/文件夹分别执行 dry run 预览：

- **文件**: `rsync -av --dry-run <file> lenovo@192.168.2.154:/home/lenovo/Workspaces/00_Inbox/01_Rsync/`
- **文件夹**: `rsync -av --dry-run --exclude='.DS_Store' <folder>/ lenovo@192.168.2.154:/home/lenovo/Workspaces/00_Inbox/01_Rsync/<folder_name>/`

注意：文件夹同步时在目标端保留文件夹名称，避免内容散落到收件箱根目录。

审查输出确认无误后继续。

## 5. 执行同步

将 dry run 中的 `--dry-run` 替换为 `--progress`，逐个执行实际同步：

- **文件**: `rsync -av --progress <file> lenovo@192.168.2.154:/home/lenovo/Workspaces/00_Inbox/01_Rsync/`
- **文件夹**: `rsync -av --progress --exclude='.DS_Store' <folder>/ lenovo@192.168.2.154:/home/lenovo/Workspaces/00_Inbox/01_Rsync/<folder_name>/`

## 6. 验证同步结果

```bash
ssh lenovo@192.168.2.154 "ls -lah /home/lenovo/Workspaces/00_Inbox/01_Rsync/"
```

## 7. 完成通知

告知用户同步结果摘要：成功推送的文件/文件夹列表、传输大小。如有失败项，给出具体原因。
