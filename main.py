import asyncio
import re
from datetime import datetime, timedelta
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
        await page.goto(target['url'], wait_until="networkidle", timeout=60000)
        await page.wait_for_selector("table", timeout=15000)
        
        rows = await page.query_selector_all("table tbody tr")
        for row in rows:
            cells = await row.query_selector_all("td")
            if len(cells) < 2: continue
            
            title_element = None
            for cell in cells:
                title_element = await cell.query_selector("a")
                if title_element: break
            
            if not title_element: continue
            
            item_title = (await title_element.inner_text()).strip()
            if "검색된 결과가 없습니다" in item_title: continue

            link_attr = await title_element.get_attribute("href") or ""
            full_link = f"https://www.scourt.go.kr{link_attr}" if link_attr.startswith("/") else link_attr

            item_date = ""
            for cell in cells:
                text = (await cell.inner_text()).strip()
                match = re.search(r'(\d{4})[-.](\d{2})[-.](\d{2})', text)
                if match:
                    item_date = text.replace('.', '-')
                    break
            
            if not item_date:
                item_date = datetime.now().strftime('%Y-%m-%d')

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
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        all_entries = []
        for target in TARGETS:
            entries = await get_entries_from_url(page, target)
            all_entries.extend(entries)
        
        if not all_entries:
            await browser.close()
            return

        # 1. 날짜로 1차 정렬 (최신 날짜가 위로)
        all_entries.sort(key=lambda x: x['date'], reverse=True)

        fg = FeedGenerator()
        fg.title('대법원 통합 소식 (실시간 적재)')
        fg.link(href='https://www.scourt.go.kr', rel='alternate')
        fg.description('모든 게시판의 글을 시간순으로 쌓아 올린 통합 피드입니다.')

        # 2. [핵심] 가상 타임스탬프 부여
        # 현재 시간에서 1분씩 차감하며 pubDate를 생성하여 리더기 내 순서를 고정함
        base_time = datetime.now()
        
        for i, item in enumerate(all_entries[:50]): # 최신 50개
            fe = fg.add_entry()
            fe.id(item['link'])
            fe.title(item['title'])
            fe.link(href=item['link'])
            
            # 수집된 순서대로 1분씩 과거로 설정하여 리더기가 '가장 위'부터 인식하게 함
            virtual_time = base_time - timedelta(minutes=i)
            # 날짜 정보는 사이트 정보를 따르되, 시간 정보만 가상으로 부여
            final_pub_date = datetime.strptime(item['date'], '%Y-%m-%d').replace(
                hour=virtual_time.hour, minute=virtual_time.minute, second=virtual_time.second
            )
            fe.published(final_pub_date.strftime('%Y-%m-%d %H:%M:%S +0900'))

        fg.rss_file('scourt_integrated.xml')
        print(f"✨ 통합 완료: 최신 정보가 가장 위로 오도록 {len(all_entries)}개를 정렬했습니다.")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
