import asyncio
from typing import Dict
import sys
from playwright.async_api import async_playwright, Page, Browser

class RobustScraper:
    """
    A scraper optimized for speed:
    - Uses a single browser context and page for multiple scrapes (if desired).
    - Minimizes waiting by using lighter load states.
    - Optionally reduces overhead like excessive scrolling/waiting.
    """

    def __init__(self):
        self._browser: Browser = None
        self._playwright = None
        self._playwright_context = None
        self._page: Page = None
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
            # Launch the browser once and keep it running
            self._browser = await self._playwright.chromium.launch(headless=True)
            # Create a single persistent context and page
            context = await self._browser.new_context()
            self._page = await context.new_page()
            self._initialized = True
            print("[Scraper] Browser and page initialized successfully", file=sys.stderr)
        except Exception as e:
            print(f"[Scraper] Failed to initialize browser: {e}", file=sys.stderr)
            await self.cleanup()
            raise

    async def cleanup(self):
        self._shutdown = True
        if self._browser:
            try:
                await self._browser.close()
            except Exception as e:
                print(f"[Scraper] Error closing browser: {e}", file=sys.stderr)
            self._browser = None

        if self._playwright_context:
            try:
                await self._playwright_context.__aexit__(None, None, None)
            except Exception as e:
                print(f"[Scraper] Error stopping playwright: {e}", file=sys.stderr)
            self._playwright = None
            self._playwright_context = None

        self._page = None
        self._initialized = False

    async def search_and_scrape(self, query: str) -> Dict[str, str]:
        """
        Scrape a given URL or domain quickly.
        
        Steps taken to maximize speed:
        - Reuse a single page and browser context.
        - Use simpler wait conditions.
        - Limit unnecessary scrolling if the page loads static content fast enough.
        """
        if self._shutdown or not self._initialized:
            raise RuntimeError("Scraper not running or browser not initialized.")

        # Construct URL
        url = f"https://{query}" if not query.startswith(('http://', 'https://')) else query
        print(f"[Scraper] Loading URL: {url}", file=sys.stderr)

        # Navigate with less strict waiting criteria for speed
        # 'load' waits for the load event, usually faster than 'networkidle'
        await self._page.goto(url, wait_until='load', timeout=60000)

        # Optional: If dynamic content is needed, attempt a quick scroll
        await self._auto_scroll(self._page)

        # Try waiting a short while for any late-loading content
        # Shorter timeout for speed
        try:
            await self._page.wait_for_load_state('domcontentloaded', timeout=5000)
        except asyncio.TimeoutError:
            print("[Scraper] DOM content load check timed out, continuing anyway", file=sys.stderr)

        # Ensure body is present
        try:
            await self._page.wait_for_selector('body', timeout=5000)
        except asyncio.TimeoutError:
            print("[Scraper] 'body' selector not found quickly, continuing with what we have", file=sys.stderr)

        # Extract content
        content = await self._extract_content(self._page)
        title = await self._page.title() or query
        final_url = self._page.url

        return {
            'title': title,
            'url': final_url,
            'content': content
        }

    async def _auto_scroll(self, page: Page) -> None:
        """
        Quickly scroll to bottom for dynamic content.
        Faster interval and lower total wait times.
        """
        await page.evaluate('''async () => {
            const distance = 200; 
            const maxScrollAttempts = 10; 
            for (let i = 0; i < maxScrollAttempts; i++) {
                const previousHeight = document.body.scrollHeight;
                window.scrollBy(0, distance);
                await new Promise(r => setTimeout(r, 100));
                const newHeight = document.body.scrollHeight;
                if (newHeight === previousHeight) break;
            }
        }''')

    async def _extract_content(self, page: Page) -> str:
        """
        Extract readable text content from the page quickly.
        Focus on main content selectors first, fallback to a text walker.
        """
        content = await page.evaluate('''() => {
            const selectors = ['article', 'main', 'section', 'div'];
            let text = '';
            for (const selector of selectors) {
                const elements = document.querySelectorAll(selector);
                for (const el of elements) {
                    const innerText = el.innerText.trim();
                    if (innerText) text += innerText + '\\n';
                }
            }
            if (!text) {
                // Simple fallback: grab all text nodes
                const walker = document.createTreeWalker(
                    document.body,
                    NodeFilter.SHOW_TEXT,
                    {
                        acceptNode: function(node) {
                            const parentTag = node.parentElement && node.parentElement.tagName;
                            if (parentTag && ['SCRIPT','STYLE','NOSCRIPT','IFRAME'].includes(parentTag)) {
                                return NodeFilter.FILTER_REJECT;
                            }
                            return NodeFilter.FILTER_ACCEPT;
                        }
                    }
                );
                let node;
                while ((node = walker.nextNode())) {
                    const nodeText = node.textContent.trim();
                    if (nodeText) text += nodeText + '\\n';
                }
            }
            return text.trim() || 'No content found';
        }''')
        return content
