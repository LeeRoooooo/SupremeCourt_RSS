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
    try:
        # 가급적 모든 데이터가 로드될 때까지 대기
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

            # [강화된 날짜 추출] 텍스트 내에서 날짜 패턴 탐색
            item_date = ""
            for cell in cells:
                text = (await cell.inner_text()).strip()
                # 2026-04-22 또는 2026.04.22 패턴 추출
                date_match = re.search(r'(\d{4})[-.](\d{2})[-.](\d{2})', text)
                if date_match:
                    item_date = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
                    break
            
            if item_date:
                entries.append({"title": f"[{target['name']}] {item_title}", "link": full_link, "date": item_date})
    except Exception as e:
        print(f"❌ {target['name']} 수집 에러: {e}")
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

        # [핵심 정렬] 날짜 기준 내림차순(최신순)으로 정렬 (4월 22일이 index 0번으로)
        all_entries.sort(key=lambda x: x['date'], reverse=True)

        fg = FeedGenerator()
        fg.title('대법원 통합 소식 (최신순)')
        fg.link(href='https://www.scourt.go.kr', rel='alternate')
        fg.description('대법원 주요 게시판의 소식을 최신 날짜순으로 완벽하게 정렬한 피드입니다.')

        # [가상 시간 부여] 정렬된 리스트 순서대로 시간을 깎아 내려감
        now = datetime.now()
        for i, item in enumerate(all_entries[:50]):
            fe = fg.add_entry()
            fe.id(item['link'])
            fe.title(item['title'])
            fe.link(href=item['link'])
            
            # 리스트의 첫 번째(가장 최신 날짜)가 가장 현재에 가까운 시간을 가짐
            # i가 커질수록(과거 글) 1분씩 과거 시간으로 설정
            # 실제 웹사이트 날짜(item['date'])를 기반으로 시간을 조합
            item_dt = datetime.strptime(item['date'], '%Y-%m-%d')
            pub_date = item_dt.replace(hour=now.hour, minute=now.minute, second=now.second) - timedelta(minutes=i)
            
            fe.published(pub_date.strftime('%Y-%m-%d %H:%M:%S +0900'))

        fg.rss_file('scourt_integrated.xml')
        print(f"✨ 정렬 완료: {all_entries[0]['date']} 기사가 파일 맨 위로 배치되었습니다.")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
