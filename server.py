Warning: fs was declared with const; use let for reassignable variables.
#!/usr/bin/env python3
"""报名表单服务器 + 二维码生成"""

import csv
import io
import json
import os
import html
import hmac
import re
import tempfile
import threading
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import qrcode

HOST = os.environ.get("REGISTRATION_HOST", "127.0.0.1")
PORT = int(os.environ.get("REGISTRATION_PORT", "8080"))
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "submissions.json")
QR_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qrcode.png")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "").strip()
DATA_LOCK = threading.Lock()


def load_submissions():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_submission(entry):
    with DATA_LOCK:
        subs = load_submissions()
        subs.append(entry)
        _write_submissions(subs)


def _write_submissions(subs):
    directory = os.path.dirname(DATA_FILE)
    fd, temp_path = tempfile.mkstemp(prefix="submissions-", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(subs, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, DATA_FILE)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def _csv_safe(value):
    text = str(value or "")
    if re.match(r"^[\s\x00-\x1f]*[=+\-@]", text):
        return "'" + text
    return text


class Handler(SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/api/admin/login":
            self.handle_admin_login()
        elif self.path == "/api/register":
            self.handle_register()
        elif self.path == "/api/submissions/delete":
            if not self.require_admin(): return
            self.handle_delete()
        else:
            self.send_error(404)

    def do_GET(self):
        if self.path == "/":
            self.path = "/index.html"
            super().do_GET()
        elif self.path == "/admin":
            if not self.require_admin(page=True): return
            self.serve_admin()
        elif self.path == "/api/submissions":
            if not self.require_admin(): return
            self.send_json(200, load_submissions())
        elif self.path == "/api/submissions/export":
            if not self.require_admin(): return
            self.export_csv()
        else:
            super().do_GET()

    def handle_register(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            data = json.loads(body)
            name = str(data.get("name", "")).strip()
            phone = str(data.get("phone", "")).strip()
            company = str(data.get("company", "")).strip()

            if len(name) > 30 or len(phone) > 30 or len(company) > 60:
                self.send_json(400, {"message": "字段长度超出限制"})
                return
            if not name or not phone or not company or not re.fullmatch(r"1[3-9]\d{9}", phone):
                self.send_json(400, {"message": "请填写所有字段"})
                return

            entry = {
                "name": name,
                "phone": phone,
                "company": company,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            save_submission(entry)
            print(f"[报名] {name} | {phone} | {company}")
            self.send_json(200, {"message": "报名成功"})
        except json.JSONDecodeError:
            self.send_json(400, {"message": "数据格式错误"})

    def _has_admin_session(self):
        if not ADMIN_TOKEN:
            return self.client_address[0] in {"127.0.0.1", "::1"}
        cookies = dict(item.strip().split("=", 1) for item in self.headers.get("Cookie", "").split(";") if "=" in item)
        return hmac.compare_digest(cookies.get("admin_session", ""), ADMIN_TOKEN)

    def require_admin(self, page=False):
        if self._has_admin_session():
            return True
        if page:
            body = """<!doctype html><meta charset='utf-8'><title>管理员登录</title>
            <style>body{font:16px sans-serif;max-width:360px;margin:15vh auto;padding:24px}input,button{padding:10px;margin:6px 0;width:100%}</style>
            <h1>管理员登录</h1><form id='f'><input id='t' type='password' placeholder='管理员口令' required><button>登录</button></form>
            <script>f.onsubmit=async e=>{e.preventDefault();let r=await fetch('/api/admin/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:t.value})});if(r.ok)location.reload();else alert('口令错误')}</script>"""
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers(); self.wfile.write(body.encode()); return False
        self.send_json(401, {"message": "需要管理员登录"}); return False

    def handle_admin_login(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            token = str(body.get("token", ""))
        except (json.JSONDecodeError, ValueError):
            self.send_json(400, {"message": "数据格式错误"}); return
        if ADMIN_TOKEN and hmac.compare_digest(token, ADMIN_TOKEN):
            self.send_response(200); self.send_header("Set-Cookie", f"admin_session={ADMIN_TOKEN}; HttpOnly; SameSite=Strict; Path=/"); self.end_headers(); return
        self.send_json(401, {"message": "口令错误"})

    def handle_delete(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            data = json.loads(body)
            idx = data.get("index")
            subs = load_submissions()
            if idx is not None and 0 <= idx < len(subs):
                removed = subs.pop(idx)
                with DATA_LOCK:
                    _write_submissions(subs)
                print(f"[删除] {removed.get('name')} | {removed.get('phone')}")
                self.send_json(200, {"message": "已删除"})
            else:
                self.send_json(400, {"message": "无效的索引"})
        except json.JSONDecodeError:
            self.send_json(400, {"message": "数据格式错误"})

    def export_csv(self):
        subs = load_submissions()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["序号", "姓名", "手机号", "公司名称", "报名时间"])
        for i, s in enumerate(subs, 1):
            writer.writerow([i, _csv_safe(s.get("name")), _csv_safe(s.get("phone")), _csv_safe(s.get("company")), s.get("time", "")])
        csv_content = output.getvalue()
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8-sig")
        self.send_header("Content-Disposition", f'attachment; filename="报名数据_{datetime.now().strftime("%Y%m%d")}.csv"')
        self.end_headers()
        self.wfile.write(csv_content.encode("utf-8-sig"))

    def serve_admin(self):
        subs = load_submissions()
        rows = ""
        for i, s in enumerate(subs):
            rows += f"""
            <tr>
                <td>{i + 1}</td>
                <td>{html.escape(str(s.get('name', '')))}</td>
                <td>{html.escape(str(s.get('phone', '')))}</td>
                <td>{html.escape(str(s.get('company', '')))}</td>
                <td>{html.escape(str(s.get('time', '')))}</td>
                <td><button class="del-btn" onclick="del({i})">删除</button></td>
            </tr>"""

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>报名数据管理</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif; background: #f5f6fa; padding: 20px; }}
.header {{ background: #fff; padding: 20px 24px; border-radius: 12px; margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
.header h1 {{ font-size: 20px; color: #333; }}
.header .count {{ color: #667eea; }}
.actions {{ display: flex; gap: 10px; flex-wrap: wrap; }}
.btn {{ padding: 8px 20px; border: none; border-radius: 8px; font-size: 14px; cursor: pointer; font-weight: 500; transition: opacity 0.2s; }}
.btn:active {{ opacity: 0.8; }}
.btn-primary {{ background: #667eea; color: #fff; }}
.btn-outline {{ background: #fff; color: #667eea; border: 1px solid #667eea; }}
.btn-danger {{ background: #e74c3c; color: #fff; }}
.card {{ background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
table {{ width: 100%; border-collapse: collapse; }}
th {{ background: #fafbfc; padding: 12px 16px; text-align: left; font-size: 13px; color: #888; border-bottom: 1px solid #eee; white-space: nowrap; }}
td {{ padding: 14px 16px; font-size: 14px; color: #333; border-bottom: 1px solid #f0f0f0; }}
tr:last-child td {{ border-bottom: none; }}
.del-btn {{ padding: 4px 12px; background: #fff; color: #e74c3c; border: 1px solid #e74c3c; border-radius: 6px; font-size: 12px; cursor: pointer; }}
.del-btn:hover {{ background: #e74c3c; color: #fff; }}
.empty {{ text-align: center; padding: 60px 20px; color: #999; }}
.toast {{ position: fixed; top: 20px; left: 50%; transform: translateX(-50%); background: #333; color: #fff; padding: 10px 24px; border-radius: 8px; font-size: 14px; display: none; z-index: 999; }}
@media (max-width: 768px) {{
    .header {{ flex-direction: column; align-items: flex-start; }}
    td, th {{ font-size: 12px; padding: 10px 8px; }}
}}
</style>
</head>
<body>
<div class="header">
    <div><h1>📋 报名数据管理 <span class="count">({len(subs)} 条记录)</span></h1></div>
    <div class="actions">
        <button class="btn btn-outline" onclick="location.reload()">刷新</button>
        <button class="btn btn-primary" onclick="exportCSV()">导出 CSV</button>
    </div>
</div>
<div class="card">
    {"<table><thead><tr><th>序号</th><th>姓名</th><th>手机号</th><th>公司名称</th><th>报名时间</th><th>操作</th></tr></thead><tbody>" + rows + "</tbody></table>" if subs else '<div class="empty">暂无报名数据</div>'}
</div>
<div class="toast" id="toast"></div>
<script>
async function del(idx) {{
    if (!confirm('确定删除这条报名记录？')) return;
    const res = await fetch('/api/submissions/delete', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ index: idx }})
    }});
    if (res.ok) {{ showToast('已删除'); setTimeout(() => location.reload(), 500); }}
    else {{ showToast('删除失败'); }}
}}
function exportCSV() {{ window.open('/api/submissions/export'); }}
function showToast(msg) {{
    const t = document.getElementById('toast');
    t.textContent = msg; t.style.display = 'block';
    setTimeout(() => t.style.display = 'none', 2000);
}}
</script>
</body>
</html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def send_json(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def generate_qr(url):
    qr = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#333333", back_color="#ffffff")
    img = img.convert("RGB")
    img.save(QR_FILE, "PNG")
    print(f"二维码已生成: {QR_FILE}")
    return QR_FILE


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    if HOST not in {"127.0.0.1", "localhost", "::1"} and not ADMIN_TOKEN:
        raise SystemExit("对外监听前必须设置 ADMIN_TOKEN")
    print(f"服务启动: http://{HOST}:{PORT}")
    print(f"报名数据: {DATA_FILE}")

    server = HTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
        server.shutdown()
