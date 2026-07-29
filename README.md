# 家庭物品收纳管理系统（登录注册创新版）

该版本可以上传到 GitHub，并通过 Render 部署为公开网址。

## 新增账号功能

- 独立登录页面
- 手机号和邮箱注册
- 手机号或邮箱登录
- 密码加密保存
- 安全退出登录
- 每位用户只能查看和管理自己的物品、购物清单和收纳位置
- 注册时验证手机号、邮箱和密码格式

## 原有创新功能

- 智能编号自动生成
- 收纳位置二维码
- 临期、过期和低库存提醒
- 家庭购物清单
- CSV 数据导出
- 浅棕色暖色家居风格

## 本地运行

```bash
python3 -m pip install -r requirements.txt
python3 app.py
```

浏览器打开：

```text
http://127.0.0.1:5000
```

首次打开会自动进入注册或登录页面。

## Render 部署

上传全部文件到 GitHub 后，在 Render 中连接仓库。项目中的 `render.yaml` 会自动配置：

- Build Command：`pip install -r requirements.txt`
- Start Command：`gunicorn app:app`

## 重要说明

该项目目前使用 SQLite。Render 免费服务重新部署或重启后，本地数据库可能被清空，因此适合作业展示。正式长期使用建议改用 PostgreSQL。
