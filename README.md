Warning: fs was declared with const; use let for reassignable variables.
# 报名表单与二维码示例

一个无需数据库的本地活动报名表单示例，包含报名页、管理页、CSV 导出和二维码生成脚本。

## 运行

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python3 server.py
```

打开 <http://127.0.0.1:8080>。管理页面在 `/admin`；本机运行时无需口令。若部署到受控内网或公网，先设置管理员口令：

```sh
export ADMIN_TOKEN="请替换为足够长的随机口令"
export REGISTRATION_HOST="0.0.0.0"
python3 server.py
```

打开 `/admin` 登录后才能查看、删除或导出报名数据。生成二维码：

```sh
python3 generate_qr.py "https://example.com/event"
```

项目默认绑定 `127.0.0.1`，报名数据写入当前目录的 `submissions.json`，保存采用临时文件替换以减少中断写入造成的损坏。对外监听时没有设置 `ADMIN_TOKEN` 会直接拒绝启动；仍建议配合 HTTPS、反向代理限流和数据保留策略使用。

仓库不包含历史报名记录、真实二维码或个人信息。请不要提交 `submissions.json`、生成的二维码或任何真实报名数据。

## 隐私与限制

姓名、手机号和公司名属于个人或业务数据，应只在取得必要同意后收集，并提供删除机制。管理接口没有账号体系，不能直接作为生产系统使用。当前未指定开源许可证。
