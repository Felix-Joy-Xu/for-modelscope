from DrissionPage import ChromiumPage
import time

def test_jd():
    page = ChromiumPage()
    url = "https://www.zhipin.com/job_detail/c3a95bec3c3f38390nB-3t28ElZW.html"
    page.get(url)
    
    time.sleep(3) # Wait for load or captcha
    
    page.get_screenshot(path='c:/Users/22735/Desktop/文献/hiring_crawler/jd_screenshot.png')
    
    with open('c:/Users/22735/Desktop/文献/hiring_crawler/jd_html.txt', 'w', encoding='utf-8') as f:
        f.write(page.html)
        
if __name__ == "__main__":
    test_jd()
