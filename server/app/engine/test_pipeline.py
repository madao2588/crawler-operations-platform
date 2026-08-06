import json
import traceback
from typing import Any

from app.engine.cleaner import clean_content
from app.engine.downloader import fetch_dynamic, fetch_static
from app.engine.parser import (
    detail_rules_json,
    extract_list_follow_items,
    parse_with_readability,
    parse_with_rules,
    resolve_list_page_urls,
)
from app.engine.pipeline import _load_rules
from app.engine.validator import quality_score


async def test_run(start_url: str, parser_rules: str | None = None) -> dict[str, Any]:
    notes: list[str] = []
    fetch_mode: str | None = None
    content_source: str | None = None

    try:
        parsed: dict[str, str | None] = {
            "title": None,
            "content_html": None,
            "source_url": start_url,
        }

        rules = None
        try:
            rules = _load_rules(parser_rules)
        except json.JSONDecodeError as exc:
            notes.append(f"parser_rules 不是合法 JSON：{exc!s}")
        except ValueError as exc:
            notes.append(str(exc))
        except Exception as exc:
            notes.append(f"解析 parser_rules 失败：{exc!s}")

        target_url = start_url
        fallback_title: str | None = None
        html, fetch_mode = await _fetch_test_page(start_url, rules, notes)
        if rules and rules.get("crawl_mode") == "list_follow":
            list_items: list[dict[str, str]] = []
            for list_url in resolve_list_page_urls(start_url, rules):
                if list_url != start_url:
                    html, fetch_mode = await _fetch_test_page(list_url, rules, notes)
                list_items.extend(
                    extract_list_follow_items(
                        html,
                        list_url,
                        rules,
                        url_cap=10 - len(list_items),
                    )
                )
                if list_items:
                    break
            if not list_items:
                raise ValueError("列表规则未命中任何详情链接")

            target_url = list_items[0]["url"]
            fallback_title = list_items[0].get("title")
            notes.append(f"列表命中 {len(list_items)} 条，抽测首条详情：{target_url}")
            html, fetch_mode = await _fetch_test_page(target_url, rules, notes)
            rules = _load_rules(detail_rules_json(rules))
            parsed["source_url"] = target_url

        if rules:
            try:
                parsed_rules_res = parse_with_rules(html, rules)
                parsed.update(parsed_rules_res)
                if parsed.get("content_html"):
                    content_source = "rules"
            except Exception as exc:
                notes.append(f"规则解析失败，将尝试正文抽取：{exc!s}")
        if fallback_title and not parsed.get("title"):
            parsed["title"] = fallback_title

        if not parsed.get("content_html"):
            try:
                parsed_readability = parse_with_readability(html)
                parsed.update(parsed_readability)
                if parsed.get("content_html"):
                    content_source = "readability"
            except Exception as exc:
                notes.append(f"readability 抽取失败：{exc!s}")

        if not parsed.get("content_html"):
            parsed["content_html"] = html
            content_source = "raw_html"
            notes.append("未得到有效正文 HTML，已退回原始 HTML。")

        cleaned = clean_content(parsed["content_html"])
        score = quality_score(parsed.get("title"), cleaned["content_text"])

        trace = {
            "fetch": fetch_mode,
            "content_source": content_source,
            "notes": notes,
        }

        return {
            "title": parsed.get("title"),
            "content_text": cleaned["content_text"],
            "content_html": cleaned["content_html"],
            "quality_score": score,
            "error": None,
            "trace": trace,
        }
    except Exception:
        return {
            "title": None,
            "content_text": None,
            "content_html": None,
            "quality_score": None,
            "error": traceback.format_exc(),
            "trace": {
                "fetch": fetch_mode,
                "content_source": content_source,
                "notes": notes,
            },
        }


async def _fetch_test_page(
    url: str,
    rules: dict[str, object] | None,
    notes: list[str],
) -> tuple[str, str]:
    wait_for_selector_raw = rules.get("dynamic_wait_selector") if rules else None
    wait_for_selector = (
        wait_for_selector_raw.strip()
        if isinstance(wait_for_selector_raw, str) and wait_for_selector_raw.strip()
        else None
    )
    if rules and rules.get("force_dynamic_fetch") is True:
        return (
            await fetch_dynamic(url, wait_for_selector=wait_for_selector),
            "dynamic",
        )
    try:
        return await fetch_static(url), "static"
    except Exception as static_exc:
        notes.append(f"静态抓取失败，已回退动态抓取：{static_exc!s}")
        return (
            await fetch_dynamic(url, wait_for_selector=wait_for_selector),
            "dynamic",
        )
