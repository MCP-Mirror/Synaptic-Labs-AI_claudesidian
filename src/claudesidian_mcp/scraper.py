import asyncio
from playwright.async_api import async_playwright, Page, Browser
from typing import Dict
import sys

class RobustScraper:
    def __init__(self):
        self._browser: Browser = None
        self._playwright = None
        self._playwright_context = None
        self._initialized = False
        self._shutdown = False

    async def __aenter__(self):
        await self.setup()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()

    async def setup(self):
        if self._initialized:
            return
        try:
            self._playwright_context = async_playwright()
            self._playwright = await self._playwright_context.__aenter__()
            # Ensure browsers are installed: `playwright install`
            self._browser = await self._playwright.chromium.launch(headless=True)
            self._initialized = True
            print("Browser initialized successfully", file=sys.stderr)
        except Exception as e:
            print(f"Failed to initialize browser: {e}", file=sys.stderr)
            await self.cleanup()
            raise

    async def cleanup(self):
        self._shutdown = True
        if self._browser:
            try:
                await self._browser.close()
            except Exception as e:
                print(f"Error closing browser: {e}", file=sys.stderr)
            self._browser = None

        if self._playwright_context:
            try:
                await self._playwright_context.__aexit__(None, None, None)
            except Exception as e:
                print(f"Error stopping playwright: {e}", file=sys.stderr)
            self._playwright = None
            self._playwright_context = None

        self._initialized = False

    async def _get_page(self) -> Page:
        if self._shutdown or not self._initialized:
            raise RuntimeError("Scraper is not running or browser not initialized.")
        # Create a fresh context and page each time
        context = await self._browser.new_context()
        page = await context.new_page()
        return page

    async def search_and_scrape(self, query: str) -> Dict[str, str]:
        # This is a simpler version without retries. 
        # The caller can implement retry logic if desired.
        if not self._initialized:
            raise RuntimeError("Scraper not initialized.")

        page = await self._get_page()
        try:
            # Attempt direct URL first
            url = f"https://{query}" if not query.startswith(('http://', 'https://')) else query
            print(f"Attempting to load URL: {url}", file=sys.stderr)
            await page.goto(url, wait_until='networkidle', timeout=300000)  # Changed wait_until to 'networkidle'

            # Scroll to the bottom to load dynamic content
            await self._auto_scroll(page)

            # Wait for additional network idle after scrolling
            try:
                await page.wait_for_load_state('networkidle', timeout=10000)
            except asyncio.TimeoutError:
                print("Network did not become fully idle after scrolling, continuing...", file=sys.stderr)

            await page.wait_for_selector('body', timeout=50000)

            # Enhanced content extraction
            content = await page.evaluate('''() => {
                const selectors = ['article', 'main', 'section', 'div'];
                let text = '';
                selectors.forEach(selector => {
                    const elements = document.querySelectorAll(selector);
                    elements.forEach(el => {
                        text += el.innerText + '\\n';
                    });
                });
                if (!text) {
                    // Fallback to TreeWalker if no specific selectors found
                    const walker = document.createTreeWalker(
                        document.body,
                        NodeFilter.SHOW_TEXT,
                        {
                            acceptNode: function(node) {
                                if (node.parentElement && ['SCRIPT','STYLE','NOSCRIPT','IFRAME'].includes(node.parentElement.tagName)) {
                                    return NodeFilter.FILTER_REJECT;
                                }
                                return NodeFilter.FILTER_ACCEPT;
                            }
                        }
                    );
                    let node;
                    while ((node = walker.nextNode())) {
                        text += node.textContent + '\\n';
                    }
                }
                return text.trim() || 'No content found';
            }''')

            title = await page.title() or query
            final_url = page.url

            return {
                'title': title,
                'url': final_url,
                'content': content
            }
        finally:
            await page.context.close()

    async def _auto_scroll(self, page: Page) -> None:
        """Automatically scrolls the page to load dynamic content."""
        await page.evaluate('''async () => {
            await new Promise((resolve) => {
                let totalHeight = 0;
                const distance = 100;
                const timer = setInterval(() => {
                    const scrollHeight = document.body.scrollHeight;
                    window.scrollBy(0, distance);
                    totalHeight += distance;

                    if(totalHeight >= scrollHeight){
                        clearInterval(timer);
                        resolve();
                    }
                }, 100);
            });
        }''')

# Example usage (uncomment to test):
# if __name__ == "__main__":
#     async def main():
#         async with RobustScraper() as scraper:
#             result = await scraper.search_and_scrape("example.com")
#             print(result)
#     asyncio.run(main())
