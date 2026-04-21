import asyncio
from playwright.async_api import async_playwright
from feedgen.feed import FeedGenerator

async def generate_rss():
    async with async_playwright() as p:
        # 내 컴퓨터의 Edge 사용
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 소스 코드 확인 결과, 이 주소가 확실합니다.
        target_url = "https://www.scourt.go.kr/portal/news/NewsListAction.work?gubun=6"
        print(f"🚀 분석된 소스 구조로 접속 중: {target_url}")
        
        try:
            await page.goto(target_url, wait_until="domcontentloaded")
            # 테이블이 나타날 때까지 확실히 대기
            await page.wait_for_selector("table.tableHor")

            fg = FeedGenerator()
            fg.title('대법원 보도자료 피드')
            fg.link(href=target_url, rel='alternate')
            fg.description('소스 코드 분석을 통해 최적화된 수집 결과입니다.')

            # 테이블 행(tr) 추출
            rows = await page.query_selector_all("table.tableHor tbody tr")
            
            count = 0
            for row in rows:
                cells = await row.query_selector_all("td")
                
                # [구조 분석 결과]
                # cells[0]: 번호 (mhid)
                # cells[1]: 빈 칸 (tit)
                # cells[2]: 실제 제목과 링크 (tit) -> 여기가 핵심!
                # cells[3]: 작성일
                
                if len(cells) < 4: continue
                
                # 제목 요소 추출 (3번째 td인 index 2 사용)
                title_element = await cells[2].query_selector("a")
                if not title_element: continue
                
                item_title = (await title_element.inner_text()).strip()
                item_date = (await cells[3].inner_text()).strip()
                link_attr = await title_element.get_attribute("href")
                
                # 링크 주소 생성
                full_link = f"https://www.scourt.go.kr{link_attr}" if link_attr.startswith("/") else link_attr

                fe = fg.add_entry()
                fe.id(full_link)
                fe.title(item_title)
                fe.link(href=full_link)
                fe.pubDate(f"{item_date} 09:00:00 +0900")
                count += 1

            if count > 0:
                fg.rss_file('scourt_press.xml')
                print(f"✅ 드디어 성공! {count}개의 보도자료를 수집하여 저장했습니다.")
            else:
                print("⚠️ 구조는 맞지만 데이터를 가져오지 못했습니다. 일시적인 접속 제한일 수 있습니다.")

        except Exception as e:
            print(f"❌ 오류 발생: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(generate_rss())
