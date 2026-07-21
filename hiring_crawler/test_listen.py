"""测试 DrissionPage listen 功能 - 找出 Boss 直聘的 API 接口"""
import time, json
from DrissionPage import ChromiumPage

page = ChromiumPage()
page.get("https://www.zhipin.com/web/geek/job?query=Python&city=100010000")
time.sleep(5)

# 先不登录，测试监听功能
# 尝试启动监听 - 看看所有 wapi 请求
print("正在监听 wapi 请求...")
page.listen.start("wapi")  # 监听包含 wapi 的请求

# 滚动触发加载
page.scroll.to_bottom()
time.sleep(3)

# 尝试获取响应
resp = page.listen.wait(timeout=10)
print(f"Got response: {resp}")
print(f"URL: {resp.url}")
print(f"Body keys: {list(resp.response.body.keys()) if isinstance(resp.response.body, dict) else type(resp.response.body)[:200]}")

# 再试获取 jobList
from DrissionPage.common import wait_until