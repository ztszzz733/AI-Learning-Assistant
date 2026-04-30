from __future__ import annotations

from fastapi.testclient import TestClient

from book_agent.main import app


def test_web_app_and_assets_are_served() -> None:
    client = TestClient(app)

    app_response = client.get("/app")
    css_response = client.get("/static/styles.css")
    js_response = client.get("/static/app.js")

    assert app_response.status_code == 200
    assert "Book Agent" in app_response.text
    assert "模型配置" in app_response.text
    assert "随时提问" in app_response.text
    assert "deepseek-v4-pro" in app_response.text
    assert "上一课" in app_response.text
    assert "page-window-size" in app_response.text
    assert "session-page-window-size" in app_response.text
    assert "qa-list" in app_response.text
    assert "clear-qa" in app_response.text
    assert "调整页数" in app_response.text
    assert css_response.status_code == 200
    assert js_response.status_code == 200
    assert "splitReplyIntoPages" in js_response.text
    assert "renderMarkdown" in js_response.text
    assert "code-block" in css_response.text
    assert "#{1,6}" in js_response.text
    assert "一二三四五六七八九十" in js_response.text
    assert "/settings/llm" in js_response.text
    assert "/retreat" in js_response.text
    assert "/page-window" in js_response.text
    assert "/output" in js_response.text
    assert "addQaEntry" in js_response.text
