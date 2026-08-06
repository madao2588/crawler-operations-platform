import pytest
from playwright.async_api import Error as PlaywrightError

from app.engine.downloader import _launch_chromium, _wait_for_dynamic_content


@pytest.mark.asyncio
async def test_launch_chromium_falls_back_to_system_chrome_only_when_bundle_missing() -> None:
    sentinel = object()

    class FakeChromium:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def launch(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                raise PlaywrightError("Executable doesn't exist at bundled/chromium")
            return sentinel

    chromium = FakeChromium()

    browser = await _launch_chromium(chromium, {"headless": True})

    assert browser is sentinel
    assert chromium.calls == [
        {"headless": True},
        {"headless": True, "channel": "chrome"},
    ]


@pytest.mark.asyncio
async def test_launch_chromium_does_not_mask_other_launch_errors() -> None:
    class FakeChromium:
        async def launch(self, **_kwargs):
            raise PlaywrightError("browser crashed for another reason")

    with pytest.raises(PlaywrightError, match="another reason"):
        await _launch_chromium(FakeChromium(), {"headless": True})


@pytest.mark.asyncio
async def test_wait_for_dynamic_content_uses_source_ready_selector() -> None:
    calls: list[tuple[str, int]] = []

    class FakePage:
        async def wait_for_selector(self, selector: str, *, timeout: int) -> None:
            calls.append((selector, timeout))

        async def wait_for_timeout(self, timeout: int) -> None:
            calls.append(("settle", timeout))

    await _wait_for_dynamic_content(
        FakePage(),
        wait_for_selector=".items a[href], .article-content",
        timeout_ms=45_000,
    )

    assert calls == [
        (".items a[href], .article-content", 45_000),
        ("settle", 250),
    ]
