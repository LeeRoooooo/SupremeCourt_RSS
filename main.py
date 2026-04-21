import asyncio
import re
from datetime import datetime
from playwright.async_api import async_playwright
from feedgen.feed import FeedGenerator

# 통합 수집 대상 목록
TARGETS = [
    {"name": "보도자료", "url": "https://www.scourt.go.kr/portal/news/NewsListAction.work?gubun=6"},
    {"name": "전국법원 주요판결", "url": "https://www.scourt.go.kr/portal/dcboard/DcNewsListAction.work?gubun=44"},
    {"name": "판례속보", "url": "https://www.scourt.go.kr/portal/news/NewsListAction.work?gubun=4&type=5"},
    {"name": "언론보도판결", "url": "https://www.scourt.go.kr/portal/news/NewsListAction.work?gubun=2"}
]

async def get_entries_from_url(page, target):
    entries = []
    print(f"🔎 {target['name']} 탐색 중...")
    try:
        await page.goto(target['url'], wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_selector("table.tableHor", timeout=10000)
        
        rows = await page.query_selector_all("table.tableHor tbody tr")
        for row in rows:
            cells = await row.query_selector_all("td")
            if len(cells) < 2: continue
            
            # 제목 및 링크 추출 (a 태그가 있는 칸 자동 탐색)
            title_element = None
            for cell in cells:
                title_element = await cell.query_selector("a")
                if title_element: break
            
            if not title_element: continue
            
            item_title = (await title_element.inner_text()).strip()
            link_attr = await title_element.get_attribute("href")
            full_link = f"https://www.scourt.go.kr{link_attr}" if link_attr.startswith("/") else link_attr

            # 지능형 날짜 추출 (패턴: 0000-00-00 또는 0000.00.00)
            item_date = ""
            for cell in cells:
                text = (await cell.inner_text()).strip()
                if re.match(r'^\d{4}[-.]\d{2}[-.]\d{2}$', text):
                    item_date = text.replace('.', '-')
                    break
            
            if not item_date:
                item_date = datetime.지금().strftime('%Y-%m-%d')

            entries.append({
                "title": f"[{target['name']}] {item_title}",
                "link": full_link,
                "date": item_date
            })
    except Exception as e:
        print(f"❌ {target['name']} 에러: {e}")
    return entries

async def main():
    async with async_playwright() as p:
        # 로컬 테스트 시에는 channel="msedge" 추가, GitHub 실행 시에는 아래대로 유지
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        all_entries = []
        for target in TARGETS:
            entries = await get_entries_from_url(page, target)
            all_entries.extend(entries)
        
        fg = FeedGenerator()
        fg.title('대법원 종합 소식 통합 피드')
        fg.link(href='https://www.scourt.go.kr', rel='alternate')
        fg.description('보도자료 및 주요판결 소식을 하나로 모은 통합 피드입니다.')

        # 날짜 내림차순 정렬
        all_entries.sort(key=lambda x: x['date'], reverse=True)

        for item in all_entries[:40]: # 최신 40개 항목 유지
            fe = fg.add_entry()
            fe.id(item['link'])
            fe.title(item['title'])
            fe.link(href=item['link'])
            fe.pubDate(f"{item['date']} 09:00:00 +0900")

        fg.rss_file('scourt_integrated.xml')
        print(f"✨ 통합 완료: scourt_integrated.xml 생성됨")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
