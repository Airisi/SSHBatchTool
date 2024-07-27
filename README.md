# SSH 配置管理和升级工具

## 项目概述

本项目是一个基于 PyQt5 的图形用户界面（GUI）应用程序，旨在管理多个 SSH 配置并异步执行远程主机的文件升级操作。它提供了添加、删除、导入和导出 SSH 配置信息的功能，以及一键执行所有配置主机远程升级操作的能力。

## 主要特性

- **SSH 配置管理**：添加、删除和管理多个 SSH 配置。
- **批量操作**：同时对多个远程主机执行升级操作。
- **导入/导出**：使用 CSV 文件导入和导出 SSH 配置。
- **文件选择**：通过用户友好的界面选择升级文件和脚本。
- **进度跟踪**：监控每个主机升级操作的进度。
- **异步执行**：利用异步处理提高效率。

## 文件结构

- `main.py`：主应用程序文件，包含 `MainWindow` 类和相关逻辑。
- `ssh_manager.py`：定义 `SSHManager` 类，用于处理 SSH 连接和命令执行。
- `upgrade_manager.py`：包含 `UpgradeManager` 类，用于管理远程主机升级操作。
- `main_window.ui`：定义主应用程序窗口布局的 UI 文件。
- `requirements.txt`：列出项目所需的 Python 包。

## 安装

1. 克隆仓库：
   ```
   git clone [仓库URL]
   cd [项目目录]
   ```

2. 创建并激活虚拟环境（推荐）：
   ```
   python -m venv venv
   source venv/bin/activate  # 在 Windows 上使用 venv\Scripts\activate
   ```

3. 安装依赖：
   ```
   pip install -r requirements.txt
   ```

## 使用说明

1. 运行应用程序：
   ```
   python main.py
   ```

2. 在应用程序界面中：
    - 添加 SSH 配置：输入主机地址、用户名和密码，然后点击"添加配置"。
    - 选择升级文件和脚本：点击相应的"选择文件"按钮。
    - 执行升级：点击"升级全部"按钮开始所有配置的远程升级操作。

3. 导入/导出 SSH 配置：
    - 导出：点击"导出配置"按钮，选择保存位置。
    - 导入：点击"导入配置"按钮，选择之前导出的 CSV 文件。

## 导入文件说明

### CSV 文件格式

导入的 CSV 文件应遵循以下格式：

```
Host,Username,Password
192.168.1.1,user1,password1
192.168.1.2,user2,password2
192.168.1.3,user3,password3
```

- 文件必须包含标题行，列名exactly为 `Host`、`Username` 和 `Password`。
- 每行代表一个 SSH 配置，包含主机地址、用户名和密码。
- 字段之间使用逗号(,)分隔。
- 
### 注意事项

- 确保 CSV 文件不包含额外的空行或格式错误。
- 如果导入的主机配置已存在，应用程序将跳过重复项。
- 敏感信息（如密码）将以明文形式存储在 CSV 文件中，请确保文件安全。

## 打包应用

使用 PyInstaller 打包应用程序：

1. 安装 PyInstaller：
   ```
   pip install pyinstaller
   ```

2. 运行打包命令：
   ```
   pyinstaller SSHTool.spec
   ```

3. 打包后的可执行文件将位于 `dist/UpgradeTool` 目录中。

## 注意事项

- 确保远程主机的 SSH 服务正在运行且可访问。
- 升级脚本应该能够处理传入的升级文件路径作为参数。
- 建议在执行批量升级操作前先在单个主机上测试。
- 导入大量配置时，请注意应用程序的性能可能会受到影响。

## 贡献

欢迎提交问题报告、功能请求和代码贡献。请遵循标准的 GitHub 流程：fork 仓库，创建特性分支，提交变更，并创建拉取请求。

## 许可

[MIT](https://choosealicense.com/licenses/mit/)