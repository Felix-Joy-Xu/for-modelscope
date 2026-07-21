import asyncio
from playwright.async_api import async_playwright

async def check():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        page = await b.new_page()

        print("Testing limit=10, offset=0")
        async with page.expect_response(lambda r: '/api/v1/search/job/posts' in r.url and r.request.method == 'POST') as info:
            await page.goto("https://jobs.bytedance.com/experienced/position?limit=10&offset=0")
        resp = await info.value
        r = await resp.json()
        ids0 = [j['id'] for j in r.get('data', {}).get('job_post_list', [])]
        print(f"IDs: {ids0}")

        print("Testing limit=10, offset=10")
        async with page.expect_response(lambda r: '/api/v1/search/job/posts' in r.url and r.request.method == 'POST') as info:
            await page.goto("https://jobs.bytedance.com/experienced/position?limit=10&offset=10")
        resp = await info.value
        r = await resp.json()
        ids10 = [j['id'] for j in r.get('data', {}).get('job_post_list', [])]
        print(f"IDs: {ids10}")

        print("Testing limit=1000, offset=0")
        async with page.expect_response(lambda r: '/api/v1/search/job/posts' in r.url and r.request.method == 'POST') as info:
            await page.goto("https://jobs.bytedance.com/experienced/position?limit=1000&offset=0")
        resp = await info.value
        r = await resp.json()
        ids1000_0 = [j['id'] for j in r.get('data', {}).get('job_post_list', [])]
        print(f"count: {len(ids1000_0)}")

        print("Testing limit=1000, offset=1000")
        async with page.expect_response(lambda r: '/api/v1/search/job/posts' in r.url and r.request.method == 'POST') as info:
            await page.goto("https://jobs.bytedance.com/experienced/position?limit=1000&offset=1000")
        resp = await info.value
        r = await resp.json()
        ids1000_1000 = [j['id'] for j in r.get('data', {}).get('job_post_list', [])]
        print(f"count: {len(ids1000_1000)}")

        overlap = set(ids1000_0).intersection(set(ids1000_1000))
        print(f"Overlap between offset=0 and offset=1000: {len(overlap)}")

        await b.close()

if __name__ == '__main__':
    asyncio.run(check())
