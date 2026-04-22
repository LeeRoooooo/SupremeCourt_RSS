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

            # [핵심 1] seqnum 추출 (같은 게시판 내부에서의 정렬용)
            seq_match = re.search(r'seqnum=(\d+)', link_attr)
            seq_val = int(seq_match.group(1)) if seq_match else 0

            # 날짜 추출
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
                    "board": target['name'] # [핵심 2] 정렬 시 게시판 구분을 위한 키
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
            print("⚠️ 수집된 데이터가 없습니다.")
            await browser.close()
            return

        # [핵심 3] Method 4 반영: (날짜 -> 게시판 -> 글 번호) 순으로 정렬
        # 이렇게 하면 서로 다른 게시판의 번호가 충돌하여 정렬이 꼬이는 것을 방지합니다.
        all_entries.sort(key=lambda x: (x['date'], x['board'], x['seq']), reverse=True)
        
        # 상위 60개 추출 (이 시점에서 0번 인덱스가 가장 '최신'입니다)
        top_entries = all_entries[:60]

        fg = FeedGenerator()
        fg.title('대법원 사법소식 통합 피드 (완벽 정렬)')
        fg.link(href='https://www.scourt.go.kr', rel='alternate')
        fg.description('게시판별 충돌을 방지하고 최신 정보를 상단에 배치한 피드입니다.')

        # [핵심 4] 역순(reversed)으로 Feed에 추가!! (ChatGPT가 놓친 부분)
        # feedgen은 마지막에 넣은 것을 XML 맨 위에 올립니다. 
        # 따라서 과거 글을 먼저 넣고, 가장 최신 글을 맨 마지막에 넣어야 합니다.
        for i, item in enumerate(reversed(top_entries)):
            fe = fg.add_entry()
            fe.id(item['link'])
            fe.title(item['title'])
            fe.link(href=item['link'])
            
            # i가 0(가장 오래된 글)에서 59(가장 최신 글)로 증가합니다.
            # 분(minute) 단위로 더해주면 최신 글이 가장 늦은 시간(미래)을 가지게 됩니다.
            actual_date = datetime.strptime(item['date'], '%Y-%m-%d')
            pub_dt = actual_date.replace(hour=9, minute=0, second=0) + timedelta(minutes=i)
            
            fe.published(pub_dt.strftime('%Y-%m-%d %H:%M:%S +0900'))

        fg.rss_file('scourt_integrated.xml')
        print(f"✨ 완료: {top_entries[0]['date']} 기사가 파일 최상단에 배치되었습니다.")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
