"""尝试在 Playwright 页面内 fetch 模型列表 API"""
import os, json
from playwright.sync_api import sync_playwright

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "modelscope_output")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(locale="zh-CN", viewport={"width": 1920, "height": 1080})
    page = context.new_page()

    page.goto("https://www.modelscope.cn/models", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(5000)

    # 在页面内执行 fetch（同源，可能绕过登录限制）
    print("=== 尝试页面内 fetch 模型列表 ===")
    result = page.evaluate("""async () => {
        let results = {};
        // 尝试各种POST body
        let bodies = [
            {'PageNumber': 1, 'PageSize': 3},
            {'PageNumber': 1, 'PageSize': 3, 'SortBy': 'Default'},
            {'PageNumber': 1, 'PageSize': 3, 'SortBy': 'Downloads'},
            {'PageSize': 3, 'PageNumber': 1, 'SortBy': 'Default', 'Domain': 'nlp'},
        ];
        for (let body of bodies) {
            let key = JSON.stringify(body);
            try {
                let resp = await fetch('/api/v1/models', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(body),
                });
                let data = await resp.json();
                results[key] = {
                    status: resp.status,
                    code: data.Code,
                    success: data.Success,
                    dataType: data.Data ? (Array.isArray(data.Data) ? 'array' : typeof data.Data) : null,
                    dataKeys: data.Data && typeof data.Data === 'object' ? Object.keys(data.Data).slice(0, 10) : null,
                    totalCount: data.TotalCount || (data.Data && data.Data.TotalCount) || null,
                };
            } catch(e) {
                results[key] = {error: e.message};
            }
        }
        return results;
    }""")

    for key, val in result.items():
        print(f"  Body: {key[:80]}")
        print(f"    Result: {json.dumps(val, ensure_ascii=False)[:200]}")
        print()

    # 也试试 GET 的公开 API
    print("\n=== GET 公开 API ===")
    get_results = page.evaluate("""async () => {
        let urls = {
            'licenses': '/api/v1/licenses',
            'tasks_popular': '/api/v1/tasks/popular/list',
            'tasks': '/api/v1/tasks?PageNumber=1',
            'catalogues': '/api/v1/catalogues?Business=nexa',
            'aigc_tags': '/api/v1/models/aigc/tags',
        };
        let results = {};
        for (let [name, url] of Object.entries(urls)) {
            try {
                let resp = await fetch(url);
                let data = await resp.json();
                let info = {status: resp.status, code: data.Code};
                if (data.Data) {
                    if (Array.isArray(data.Data)) {
                        info.type = 'array';
                        info.len = data.Data.length;
                    } else if (typeof data.Data === 'object') {
                        info.type = 'object';
                        info.keys = Object.keys(data.Data).slice(0, 10);
                    }
                }
                results[name] = info;
            } catch(e) {
                results[name] = {error: e.message};
            }
        }
        return results;
    }""")

    for name, info in get_results.items():
        print(f"  {name}: {json.dumps(info, ensure_ascii=False)[:150]}")

    # 保存许可证列表（很重要的治理数据）
    print("\n=== 保存许可证列表 ===")
    licenses = page.evaluate("""async () => {
        let resp = await fetch('/api/v1/licenses');
        let data = await resp.json();
        return data;
    }""")
    if licenses.get('Data', {}).get('Licenses'):
        lic_list = licenses['Data']['Licenses']
        print(f"  找到 {len(lic_list)} 个许可证:")
        for lic in lic_list[:10]:
            name = lic.get('Name', '')
            print(f"    - {name}")

    # 保存任务分类
    print("\n=== 保存任务分类 ===")
    tasks = page.evaluate("""async () => {
        let resp = await fetch('/api/v1/tasks?PageNumber=1');
        let data = await resp.json();
        return data;
    }""")
    if tasks.get('Data', {}).get('Domains'):
        domains = tasks['Data']['Domains']
        print(f"  找到 {len(domains)} 个领域:")
        for d in domains[:10]:
            name = d.get('ChineseName') or d.get('DomainName', '')
            task_count = len(d.get('Tasks', []))
            print(f"    - {name}: {task_count} tasks")

    browser.close()