# 家庭物品收纳管理系统

这是一个使用 Python、Tkinter 和 SQLite 开发的桌面客户端应用，用于管理家庭物品的分类、编号、位置、数量、状态和有效期。

## 功能

- 新增家庭物品
- 修改物品信息
- 删除物品记录
- 按关键词查询
- 按类别筛选
- 按状态筛选
- 统计物品记录数
- 统计物品总数量
- 统计30天内到期物品
- 统计已过期物品
- 导出 CSV 文件
- SQLite 本地数据库保存

## 项目结构

```text
family_storage_manager/
├── main.py
├── README.md
├── requirements.txt
├── .gitignore
└── LICENSE
```

程序第一次运行后，会自动创建：

```text
family_storage.db
```

## 运行环境

- Python 3.9 或更高版本
- Windows、macOS 或 Linux
- 不需要安装第三方 Python 库

## 运行方法

在终端进入项目文件夹：

```bash
cd family_storage_manager
```

运行程序：

```bash
python main.py
```

部分 macOS 或 Linux 电脑需要使用：

```bash
python3 main.py
```

## 上传到 GitHub

1. 登录 GitHub。
2. 点击右上角 `+`。
3. 选择 `New repository`。
4. 仓库名称填写 `family-storage-manager`。
5. 创建仓库。
6. 点击 `uploading an existing file`。
7. 将本项目中的文件拖入网页。
8. 点击 `Commit changes`。

注意：GitHub 网页不能直接上传空文件夹。本项目没有空文件夹，因此可以直接上传。

## 打包为桌面应用

先安装 PyInstaller：

```bash
pip install pyinstaller
```

在项目目录运行：

```bash
pyinstaller --onefile --windowed --name 家庭物品收纳管理系统 main.py
```

打包完成后，可执行文件位于：

```text
dist/
```

## 数据说明

所有物品信息保存在程序目录下的 `family_storage.db` 文件中。

如需备份数据，只需复制该数据库文件。

## 日期格式

购入日期和有效期统一使用：

```text
YYYY-MM-DD
```

例如：

```text
2026-07-29
```

## 许可证

本项目使用 MIT License。
