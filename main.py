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
        await page.wait_for_selector("table", timeout=20000)
        
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

            # [핵심 1] 게시판별로 다른 seqnum을 추출하여 정렬 보조 지표로 활용
            seq_match = re.search(r'seqnum=(\d+)', link_attr)
            seq_val = int(seq_match.group(1)) if seq_match else 0

            # [핵심 2] 날짜 추출
            item_date = ""
            for cell in cells:
                text = (await cell.inner_text()).strip()
                match = re.search(r'(\d{4})[-.](\d{2})[-.](\d{2})', text)
                if match:
                    item_date = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
                    break
            
            if item_date:
                entries.append({
                    "title": f"[{target['name']}] {item_title}",
                    "link": full_link,
                    "date": item_date,
                    "seq": seq_val,
                    "board": target['name'] # 디버깅용
                })
    except Exception as e:
        print(f"❌ {target['name']} 에러: {e}")
    return entries

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 1. 모든 게시판 글을 하나의 리스트로 통합
        all_entries = []
        for target in TARGETS:
            entries = await get_entries_from_url(page, target)
            all_entries.extend(entries)
        
        if not all_entries:
            print("⚠️ 수집된 데이터가 없습니다.")
            await browser.close()
            return

        # 2. [완전 통합 정렬] 
        # 게시판 구분 없이 '날짜'를 1순위, '게시물 번호'를 2순위로 하여 내림차순 정렬
        # 이렇게 하면 서로 다른 게시판 글들이 날짜와 최신성만 가지고 뒤섞입니다.
        all_entries.sort(key=lambda x: (x['date'], x['seq']), reverse=True)

        fg = FeedGenerator()
        fg.title('대법원 사법소식 통합 피드 (최신순)')
        fg.link(href='https://www.scourt.go.kr', rel='alternate')
        fg.description('모든 게시판의 소식을 시간순으로 완벽하게 통합한 피드입니다.')

        # 3. 정렬된 순서대로 XML 파일 상단부터 채우기
        now = datetime.now()
        for i, item in enumerate(all_entries[:60]): # 상위 60개 유지
            fe = fg.add_entry()
            fe.id(item['link'])
            fe.title(item['title'])
            fe.link(href=item['link'])
            
            # 4. [가상 시간 부여] 정렬 순서에 따라 1초씩 차이를 둠
            # 리더기가 파일 상단에 있는 글을 '가장 최신'으로 인식하도록 강제
            pub_dt = datetime.strptime(item['date'], '%Y-%m-%d').replace(
                hour=23, minute=59, second=59
            ) - timedelta(seconds=i)
            
            fe.published(pub_dt.strftime('%Y-%m-%d %H:%M:%S +0900'))

        fg.rss_file('scourt_integrated.xml')
        print(f"✨ 통합 완료: {len(all_entries)}개 게시물 중 최신 60개를 시간순으로 정렬했습니다.")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
