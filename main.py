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
        # networkidle을 사용하여 자바스크립트 실행이 끝날 때까지 대기
        await page.goto(target['url'], wait_until="networkidle", timeout=60000)
        
        # tableHor가 없을 경우를 대비해 일반 table 태그로 시도
        try:
            await page.wait_for_selector("table", timeout=15000)
        except:
            print(f"⚠️ {target['name']}: 테이블을 찾을 수 없습니다.")
            return []

        # 모든 테이블 행(tr)을 가져오되, 헤더(th)가 포함된 행은 제외
        rows = await page.query_selector_all("table tbody tr")
        print(f"   -> {len(rows)}개의 행 발견")

        for row in rows:
            cells = await row.query_selector_all("td")
            if len(cells) < 2: continue
            
            # 제목 및 링크 추출 (모든 칸에서 a 태그 탐색)
            title_element = None
            for cell in cells:
                title_element = await cell.query_selector("a")
                if title_element: break
            
            if not title_element: continue
            
            item_title = (await title_element.inner_text()).strip()
            # 검색결과 없음 처리
            if "검색된 결과가 없습니다" in item_title: continue

            link_attr = await title_element.get_attribute("href")
            full_link = f"https://www.scourt.go.kr{link_attr}" if link_attr and link_attr.startswith("/") else link_attr

            # 날짜 추출 (Regex 보강)
            item_date = ""
            for cell in cells:
                text = (await cell.inner_text()).strip()
                # 0000-00-00 또는 0000.00.00 패턴
                match = re.search(r'(\d{4})[-.](\d{2})[-.](\d{2})', text)
                if match:
                    item_date = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
                    break
            
            # 날짜를 못 찾으면 오늘 날짜로 (now() 수정)
            if not item_date:
                item_date = datetime.now().strftime('%Y-%m-%d')

            entries.append({
                "title": f"[{target['name']}] {item_title}",
                "link": full_link,
                "date": item_date
            })
    except Exception as e:
        print(f"❌ {target['name']} 수집 중 에러 발생: {e}")
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
            print("⚠️ 수집된 데이터가 하나도 없습니다. 스크립트를 종료합니다.")
            await browser.close()
            return

        fg = FeedGenerator()
        fg.title('대법원 종합 소식 통합 피드')
        fg.link(href='https://www.scourt.go.kr', rel='alternate')
        fg.description('대법원 주요 게시판의 소식을 하나로 모은 피드입니다.')

        # 날짜순 정렬 (YYYY-MM-DD 문자열 정렬)
        all_entries.sort(key=lambda x: x['date'], reverse=True)

        for item in all_entries[:50]:
            fe = fg.add_entry()
            fe.id(item['link'])
            fe.title(item['title'])
            fe.link(href=item['link'])
            fe.pubDate(f"{item['date']} 09:00:00 +0900")

        fg.rss_file('scourt_integrated.xml')
        print(f"✨ 통합 완료: scourt_integrated.xml 생성됨 (총 {len(all_entries)}개)")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
