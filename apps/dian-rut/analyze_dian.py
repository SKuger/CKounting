import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        print("Navigating...")
        await page.goto("https://muisca.dian.gov.co/WebRutMuisca/DefConsultaEstadoRUT.faces")
        content = await page.content()
        with open("dian_page.html", "w") as f:
            f.write(content)
        print("Done. Wrote dian_page.html")
        await browser.close()
        
asyncio.run(main())
