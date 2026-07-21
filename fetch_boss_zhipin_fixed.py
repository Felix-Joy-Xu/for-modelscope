import json
import time
from DrissionPage import ChromiumPage

OUTPUT_JSON = r"C:\Users\22735\Desktop\文献\boss_ai_jds_raw.json"

def scrape_boss():
    print("=" * 60)
    print("检测到用户已登录，重新接管 Boss 直聘浏览器...")
    print("=" * 60)
    
    # 唤起本地真实浏览器
    page = ChromiumPage()
    
    # 既然您已经登录，我们直接跳过所有等待，直捣黄龙进入搜索页
    search_url = "https://www.zhipin.com/web/geek/job?query=AI大模型&city=100010000"
    page.get(search_url)
    
    print("\n>>> 已跳转至搜索页，开始全量抓取！ <<<")
    
    all_jds = []
    page_num = 1
    
    while True:
        print(f"\n正在全量抓取第 {page_num} 页...")
        
        # 修复了刚才因为网速慢或反爬导致的加载判定问题
        if not page.ele('.job-card-wrapper', timeout=10):
            print(">> 等待 10 秒后，当前页面依然未加载出职位列表，可能是无结果或触发了反爬验证。抓取结束。")
            break
            
        job_cards = page.eles('.job-card-wrapper')
        if not job_cards:
            break
            
        for i, card in enumerate(job_cards):
            try:
                card.click()
                time.sleep(2) # 模拟人类阅读延迟
                
                detail_box = page.ele('.job-detail-box', timeout=3)
                if detail_box:
                    title = page.ele('.name', timeout=2).text if page.ele('.name') else "未知职位"
                    company = page.ele('.company-info', timeout=2).text if page.ele('.company-info') else "未知公司"
                    jd_text = page.ele('.job-detail-section', timeout=2).text if page.ele('.job-detail-section') else ""
                    
                    if jd_text:
                        all_jds.append({
                            "title": title,
                            "company": company,
                            "jd_text": jd_text,
                            "source": "BossZhipin"
                        })
                        print(f"  [{len(all_jds)}] 成功提取: {title} - {company}")
            except Exception as e:
                print(f"  提取卡片失败: {e}")
                
        # 翻页逻辑
        try:
            next_btn = page.ele('.ui-icon-arrow-right', timeout=2)
            if next_btn:
                parent_li = next_btn.parent()
                if 'disabled' in parent_li.attr('class', ''):
                    print("已到达最后一页，全量抓取结束。")
                    break
                else:
                    next_btn.click()
                    page_num += 1
                    time.sleep(4)
            else:
                print("未找到下一页按钮，抓取结束。")
                break
        except Exception as e:
            print(f"翻页异常: {e}")
            break
            
    print(f"\n抓取彻底完成！共收集到 {len(all_jds)} 份 Boss 直聘真实 JD。")
    
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(all_jds, f, ensure_ascii=False, indent=2)
    print(f"数据已安全保存至: {OUTPUT_JSON}")

if __name__ == "__main__":
    scrape_boss()
