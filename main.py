import asyncio
import re
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from feedgen.feed import FeedGenerator

TARGETS = [
    {"name": "보도자료", "url": "https://www.scourt.go.kr/portal/news/NewsListAction.work?gubun=6"},
    {"name": "전국법원 주요판결", "url": "https://www.scourt.go.kr/portal/dcboard/DcNewsListAction.work?gubun=44"},
    {"name": "판례속보", "url": "https://www.scourt.go.kr/portal/news/NewsListAction.work?gubun=4&type=5"},
    {"name": "언론보도판결", "url": "https://www.scourt.go.kr/portal/news/NewsListAction.work?gubun=2"}
]

async def get_entries_from_url(page, target):
    entries = []
    print(f"🔎 {target['name']} 수집 중...")
    try:
        await page.goto(target['url'], wait_until="networkidle", timeout=60000)
        await page.wait_for_selector("table", timeout=15000)
        
        rows = await page.query_selector_all("table tbody tr")
        for row in rows:
            cells = await row.query_selector_all("td")
            if len(cells) < 2: continue
            
            title_element = await row.query_selector("a")
            if not title_element: continue
            
            item_title = (await title_element.inner_text()).strip()
            if "검색된 결과가 없습니다" in item_title: continue
            
            link_attr = await title_element.get_attribute("href") or ""
            full_link = f"https://www.scourt.go.kr{link_attr}" if link_attr.startswith("/") else link_attr

            # 날짜 정밀 추출 (YYYY-MM-DD)
            item_date = ""
            for cell in cells:
                text = (await cell.inner_text()).strip()
                date_match = re.search(r'(\d{4})[-.](\d{2})[-.](\d{2})', text)
                if date_match:
                    item_date = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
                    break
            
            if item_date:
                entries.append({"title": f"[{target['name']}] {item_title}", "link": full_link, "date": item_date})
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

        # [핵심 1] 전체 날짜 기준 내림차순 정렬 (최신 날짜가 index 0번으로)
        all_entries.sort(key=lambda x: x['date'], reverse=True)

        fg = FeedGenerator()
        fg.title('대법원 통합 소식 (최신순)')
        fg.link(href='https://www.scourt.go.kr', rel='alternate')
        fg.description('모든 게시판의 소식을 최신 날짜순으로 정렬한 피드입니다.')

        # [핵심 2] 정렬된 리스트의 순서대로(index 0부터) RSS 항목을 생성
        # 파일의 가장 윗부분에 가장 최신 글이 놓이게 됩니다.
        for i, item in enumerate(all_entries[:50]): # 최신 50개만 유지
            fe = fg.add_entry()
            fe.id(item['link'])
            fe.title(item['title'])
            fe.link(href=item['link'])
            
            # [핵심 3] 실제 게시판 날짜를 살리되, 같은 날짜 내에서도 순서를 위해 1초씩 차이 부여
            # 23:59:59에서 1초씩 빼면서 저장 (최신글이 가장 늦은 시간을 갖게 함)
            actual_date = datetime.strptime(item['date'], '%Y-%m-%d')
            virtual_pub_date = actual_date.replace(hour=23, minute=59, second=59) - timedelta(seconds=i)
            
            fe.published(virtual_pub_date.strftime('%Y-%m-%d %H:%M:%S +0900'))

        fg.rss_file('scourt_integrated.xml')
        print(f"✨ 정렬 및 파일 생성 완료: {all_entries[0]['date']} 기사가 최상단에 배치되었습니다.")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
