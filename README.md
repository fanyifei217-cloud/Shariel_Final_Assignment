# 家庭物品收纳管理系统（Render 网页版）

这是一个可以上传到 GitHub，并部署到 Render 的 Flask Web 应用。

## 主要功能

- 新增、修改和删除家庭物品
- 设置分类、编号、房间、具体存放位置和数量
- 按关键词、类别和状态查询
- 自动识别 30 天内到期物品和已过期物品
- 首页统计物品记录数、物品总数量、即将过期数量和已过期数量
- 导出 CSV 文件
- 适配电脑和手机浏览器

## 项目结构

```text
family_storage_render/
├── app.py
├── requirements.txt
├── render.yaml
├── README.md
├── .gitignore
├── templates/
│   ├── index.html
│   └── form.html
└── static/
    └── style.css
```

## 本地运行

先安装依赖：

```bash
python3 -m pip install -r requirements.txt
```

运行：

```bash
python3 app.py
```

浏览器打开：

```text
http://127.0.0.1:5000
```

## 上传 GitHub

1. 解压本项目。
2. 在 GitHub 创建新仓库。
3. 点击 `uploading an existing file`。
4. 上传解压后的全部文件和文件夹。
5. 点击 `Commit changes`。

不要只上传 ZIP 文件。

## 部署到 Render

1. 登录 Render。
2. 点击 `New`。
3. 选择 `Blueprint`。
4. 连接存放本项目的 GitHub 仓库。
5. Render 会自动读取 `render.yaml`。
6. 点击部署。
7. 部署成功后，Render 会生成公开网址。

也可以选择 `New` → `Web Service`，并填写：

- Build Command：`pip install -r requirements.txt`
- Start Command：`gunicorn app:app`

## 数据说明

默认使用 SQLite 数据库 `family_storage.db`。

Render 免费实例的本地文件在重新部署或重启时可能被清除，因此该版本适合课程展示和功能演示。正式长期使用时建议改用 PostgreSQL。
