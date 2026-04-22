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

            # 1. 날짜 텍스트 추출
            date_text = ""
            for cell in cells:
                text = (await cell.inner_text()).strip()
                match = re.search(r'(\d{4})[-.](\d{2})[-.](\d{2})', text)
                if match:
                    date_text = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
                    break
            
            if date_text:
                # 2. [핵심] 글자를 '시간 객체'로 변환 (정렬을 위해)
                dt_obj = datetime.strptime(date_text, '%Y-%m-%d')
                entries.append({
                    "title": f"[{target['name']}] {item_title}",
                    "link": full_link,
                    "dt_obj": dt_obj  # 정렬용 객체
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

        # 3. [핵심] 수집된 모든 데이터를 시간 객체 기준으로 내림차순 정렬
        # 이제 4월 22일 글이 리스트의 무조건 0번에 옵니다.
        all_entries.sort(key=lambda x: x['dt_obj'], reverse=True)

        fg = FeedGenerator()
        fg.title('대법원 통합 소식 (최신순 정렬 완료)')
        fg.link(href='https://www.scourt.go.kr', rel='alternate')
        fg.description('날짜 객체 정렬을 통해 최신 정보를 상단에 배치한 피드입니다.')

        # 4. 정렬된 순서대로 XML 항목 추가
        # 리스트의 앞부분(최신글)부터 추가되므로 파일의 물리적 상단에 위치하게 됩니다.
        base_now = datetime.now()
        for i, item in enumerate(all_entries[:50]):
            fe = fg.add_entry()
            fe.id(item['link'])
            fe.title(item['title'])
            fe.link(href=item['link'])
            
            # 같은 날짜 글들 사이에서도 순서를 주기 위해 미세한 시간 차이 부여
            # 정렬된 순서대로 i(분)만큼 빼서 시간을 할당함
            final_date = item['dt_obj'].replace(
                hour=base_now.hour, minute=base_now.minute, second=base_now.second
            ) - timedelta(minutes=i)
            
            fe.published(final_date.strftime('%Y-%m-%d %H:%M:%S +0900'))

        fg.rss_file('scourt_integrated.xml')
        print(f"✨ 정렬 완료: {all_entries[0]['dt_obj'].strftime('%Y-%m-%d')} 소식이 상단에 배치되었습니다.")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
