"""Modern context menu styling replicating Clawd on Desk UI."""

from __future__ import annotations

from pathlib import Path


def get_menu_stylesheet() -> str:
    """Return polished QSS styling for QMenu with slender chevron-right arrows."""
    arrow_normal = (Path("assets/icons/chevron_right.png")).resolve().as_posix()
    arrow_hover = (Path("assets/icons/chevron_right_hover.png")).resolve().as_posix()

    return f"""
        QMenu {{
            background-color: #ffffff;
            border: 1px solid rgba(0, 0, 0, 0.08);
            border-radius: 12px;
            padding: 6px;
            color: #18181b;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                "PingFang SC", "Microsoft YaHei", Roboto, sans-serif;
            font-size: 13px;
        }}
        QMenu::item {{
            padding: 7px 24px 7px 14px;
            border-radius: 6px;
            margin: 2px 2px;
            color: #18181b;
        }}
        QMenu::item:selected {{
            background-color: #f4f4f5;
            color: #09090b;
        }}
        QMenu::item:disabled {{
            color: #a1a1aa;
        }}
        QMenu::separator {{
            height: 1px;
            background-color: rgba(0, 0, 0, 0.06);
            margin: 5px 8px;
        }}
        QMenu::right-arrow {{
            image: url("{arrow_normal}");
            width: 14px;
            height: 14px;
            margin-right: 6px;
        }}
        QMenu::right-arrow:selected {{
            image: url("{arrow_hover}");
        }}
    """
