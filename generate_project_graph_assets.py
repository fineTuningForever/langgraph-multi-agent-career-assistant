from __future__ import annotations

import math
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
SVG_PATH = ROOT / "PROJECT_GRAPH.svg"
PNG_PATH = ROOT / "PROJECT_GRAPH.png"

WIDTH = 2400
HEIGHT = 1850
BACKGROUND = "#FFFFFF"

COLORS = {
    "graph_fill": "#F6FFED",
    "graph_stroke": "#389E0D",
    "node_fill": "#E6F4FF",
    "node_stroke": "#1677FF",
    "state_fill": "#F9F0FF",
    "state_stroke": "#722ED1",
    "note_fill": "#FFF7E6",
    "note_stroke": "#D48806",
    "text": "#1F1F1F",
    "muted": "#595959",
    "arrow": "#434343",
}


def pick_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


FONT_TITLE = pick_font(22, bold=True)
FONT_TEXT = pick_font(18)
FONT_SMALL = pick_font(16)
FONT_CLUSTER = pick_font(20, bold=True)


def draw_multiline_center(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], lines: list[str], font, fill: str) -> None:
    x, y, w, h = box
    line_heights = []
    widths = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])
    total_height = sum(line_heights) + max(0, len(lines) - 1) * 6
    current_y = y + (h - total_height) / 2
    for line, text_w, text_h in zip(lines, widths, line_heights):
        current_x = x + (w - text_w) / 2
        draw.text((current_x, current_y), line, font=font, fill=fill)
        current_y += text_h + 6


def svg_multiline_center(x: int, y: int, w: int, h: int, lines: list[str], size: int = 18, fill: str | None = None, weight: str = "400") -> str:
    fill = fill or COLORS["text"]
    line_gap = size + 6
    total_height = line_gap * len(lines) - 6
    start_y = y + (h - total_height) / 2 + size
    parts = [
        f'<text x="{x + w / 2:.1f}" y="{start_y:.1f}" text-anchor="middle" '
        f'font-size="{size}" font-weight="{weight}" fill="{fill}" font-family="PingFang SC, Helvetica, Arial, sans-serif">'
    ]
    for idx, line in enumerate(lines):
        dy = 0 if idx == 0 else line_gap
        parts.append(f'<tspan x="{x + w / 2:.1f}" dy="{dy}">{escape(line)}</tspan>')
    parts.append("</text>")
    return "".join(parts)


def draw_box(draw: ImageDraw.ImageDraw, xywh: tuple[int, int, int, int], fill: str, stroke: str, lines: list[str], radius: int = 18, width: int = 3, font=FONT_TEXT) -> None:
    x, y, w, h = xywh
    draw.rounded_rectangle((x, y, x + w, y + h), radius=radius, fill=fill, outline=stroke, width=width)
    draw_multiline_center(draw, xywh, lines, font, COLORS["text"])


def svg_box(x: int, y: int, w: int, h: int, fill: str, stroke: str, lines: list[str], radius: int = 18, stroke_width: int = 3, font_size: int = 18, font_weight: str = "400") -> str:
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" ry="{radius}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>'
        + svg_multiline_center(x, y, w, h, lines, size=font_size, weight=font_weight)
    )


def draw_cluster(draw: ImageDraw.ImageDraw, xywh: tuple[int, int, int, int], title: str) -> None:
    x, y, w, h = xywh
    draw.rounded_rectangle((x, y, x + w, y + h), radius=22, outline=COLORS["graph_stroke"], width=3, fill=None)
    draw.rectangle((x + 20, y - 18, x + 260, y + 20), fill=BACKGROUND)
    draw.text((x + 30, y - 12), title, font=FONT_CLUSTER, fill=COLORS["graph_stroke"])


def svg_cluster(x: int, y: int, w: int, h: int, title: str) -> str:
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="22" ry="22" fill="none" '
        f'stroke="{COLORS["graph_stroke"]}" stroke-width="3"/>'
        f'<rect x="{x + 20}" y="{y - 18}" width="300" height="38" fill="{BACKGROUND}"/>'
        f'<text x="{x + 30}" y="{y + 8}" font-size="20" font-weight="600" '
        f'fill="{COLORS["graph_stroke"]}" font-family="PingFang SC, Helvetica, Arial, sans-serif">{escape(title)}</text>'
    )


def draw_diamond(draw: ImageDraw.ImageDraw, center: tuple[int, int], size: tuple[int, int], lines: list[str]) -> None:
    cx, cy = center
    w, h = size
    points = [(cx, cy - h // 2), (cx + w // 2, cy), (cx, cy + h // 2), (cx - w // 2, cy)]
    draw.polygon(points, fill=COLORS["node_fill"], outline=COLORS["node_stroke"])
    draw_multiline_center(draw, (cx - w // 2 + 10, cy - h // 2 + 10, w - 20, h - 20), lines, FONT_TEXT, COLORS["text"])


def svg_diamond(cx: int, cy: int, w: int, h: int, lines: list[str]) -> str:
    points = f"{cx},{cy - h // 2} {cx + w // 2},{cy} {cx},{cy + h // 2} {cx - w // 2},{cy}"
    return (
        f'<polygon points="{points}" fill="{COLORS["node_fill"]}" stroke="{COLORS["node_stroke"]}" stroke-width="3"/>'
        + svg_multiline_center(cx - w // 2 + 10, cy - h // 2 + 10, w - 20, h - 20, lines, size=18)
    )


def draw_arrow(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], dashed: bool = False, width: int = 4) -> None:
    if dashed:
        for start, end in zip(points, points[1:]):
            draw_dashed_segment(draw, start, end, width=width)
    else:
        draw.line(points, fill=COLORS["arrow"], width=width)
    draw_arrow_head(draw, points[-2], points[-1], width=width)


def draw_dashed_segment(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], width: int = 4, dash: int = 12, gap: int = 8) -> None:
    sx, sy = start
    ex, ey = end
    dx = ex - sx
    dy = ey - sy
    length = math.hypot(dx, dy)
    if length == 0:
        return
    ux = dx / length
    uy = dy / length
    progress = 0
    while progress < length:
        seg_end = min(progress + dash, length)
        x1 = sx + ux * progress
        y1 = sy + uy * progress
        x2 = sx + ux * seg_end
        y2 = sy + uy * seg_end
        draw.line((x1, y1, x2, y2), fill=COLORS["arrow"], width=width)
        progress += dash + gap


def draw_arrow_head(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], width: int = 4) -> None:
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    size = 14
    left = (
        end[0] - size * math.cos(angle - math.pi / 6),
        end[1] - size * math.sin(angle - math.pi / 6),
    )
    right = (
        end[0] - size * math.cos(angle + math.pi / 6),
        end[1] - size * math.sin(angle + math.pi / 6),
    )
    draw.polygon([end, left, right], fill=COLORS["arrow"])


def svg_arrow(points: list[tuple[int, int]], dashed: bool = False, width: int = 4) -> str:
    path = " ".join(("M" if idx == 0 else "L") + f" {x} {y}" for idx, (x, y) in enumerate(points))
    start = points[-2]
    end = points[-1]
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    size = 14
    left = (
        end[0] - size * math.cos(angle - math.pi / 6),
        end[1] - size * math.sin(angle - math.pi / 6),
    )
    right = (
        end[0] - size * math.cos(angle + math.pi / 6),
        end[1] - size * math.sin(angle + math.pi / 6),
    )
    dash_attr = ' stroke-dasharray="10 8"' if dashed else ""
    return (
        f'<path d="{path}" fill="none" stroke="{COLORS["arrow"]}" stroke-width="{width}"{dash_attr}/>'
        f'<polygon points="{end[0]},{end[1]} {left[0]:.1f},{left[1]:.1f} {right[0]:.1f},{right[1]:.1f}" fill="{COLORS["arrow"]}"/>'
    )


def render() -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{BACKGROUND}"/>',
    ]

    title = "基于 LangGraph 的轻量多智能体实习求职助手 - Graph 结构图"
    draw.text((60, 30), title, font=pick_font(28, bold=True), fill=COLORS["text"])
    svg_parts.append(
        f'<text x="60" y="58" font-size="28" font-weight="700" fill="{COLORS["text"]}" '
        f'font-family="PingFang SC, Helvetica, Arial, sans-serif">{escape(title)}</text>'
    )

    subtitle = "体现主图、子图、Command 更新与跳转、Send 并行汇总、以及低分回路触发条件"
    draw.text((60, 72), subtitle, font=FONT_TEXT, fill=COLORS["muted"])
    svg_parts.append(
        f'<text x="60" y="98" font-size="18" fill="{COLORS["muted"]}" '
        f'font-family="PingFang SC, Helvetica, Arial, sans-serif">{escape(subtitle)}</text>'
    )

    clusters = [
        ((40, 120, 2320, 670), "主图 Main Graph"),
        ((120, 900, 930, 430), "子图 job_analysis_flow"),
        ((1150, 900, 1090, 430), "子图 match_flow"),
        ((40, 1400, 2320, 360), "状态判断 / 回路说明"),
    ]
    for rect, title_text in clusters:
        draw_cluster(draw, rect, title_text)
        svg_parts.append(svg_cluster(*rect, title_text))

    boxes = [
        ((110, 190, 130, 60), COLORS["graph_fill"], COLORS["graph_stroke"], ["START"], 18, 3, FONT_TITLE, 22, "600"),
        ((310, 170, 250, 100), COLORS["node_fill"], COLORS["node_stroke"], ["supervisor_node"], 18, 3, FONT_TITLE, 22, "600"),
        ((1010, 150, 340, 120), COLORS["graph_fill"], COLORS["graph_stroke"], ["Send 并行分发", "job_analysis_flow x N"], 18, 3, FONT_TITLE, 22, "600"),
        ((1010, 330, 360, 120), COLORS["graph_fill"], COLORS["graph_stroke"], ["Send 并行分发", "match_flow x N"], 18, 3, FONT_TITLE, 22, "600"),
        ((1500, 140, 330, 100), COLORS["node_fill"], COLORS["node_stroke"], ["resume_optimizer_node"], 18, 3, FONT_TITLE, 22, "600"),
        ((1500, 330, 330, 100), COLORS["node_fill"], COLORS["node_stroke"], ["career_coach_node"], 18, 3, FONT_TITLE, 22, "600"),
        ((1990, 240, 180, 80), COLORS["node_fill"], COLORS["node_stroke"], ["finish_node"], 18, 3, FONT_TITLE, 22, "600"),
        ((2190, 250, 120, 60), COLORS["graph_fill"], COLORS["graph_stroke"], ["END"], 18, 3, FONT_TITLE, 22, "600"),

        ((220, 980, 300, 90), COLORS["node_fill"], COLORS["node_stroke"], ["extract_requirements_node"], 18, 3, FONT_TEXT, 18, "500"),
        ((220, 1120, 300, 90), COLORS["node_fill"], COLORS["node_stroke"], ["position_job_node"], 18, 3, FONT_TEXT, 18, "500"),
        ((220, 1245, 300, 70), COLORS["state_fill"], COLORS["state_stroke"], ["汇总回主图 analyses"], 18, 3, FONT_TEXT, 18, "500"),

        ((1280, 980, 300, 90), COLORS["node_fill"], COLORS["node_stroke"], ["score_match_node"], 18, 3, FONT_TEXT, 18, "500"),
        ((1280, 1120, 300, 90), COLORS["node_fill"], COLORS["node_stroke"], ["finalize_match_node"], 18, 3, FONT_TEXT, 18, "500"),
        ((1280, 1245, 340, 70), COLORS["state_fill"], COLORS["state_stroke"], ["汇总回主图 matches"], 18, 3, FONT_TEXT, 18, "500"),

        ((610, 190, 300, 85), COLORS["note_fill"], COLORS["note_stroke"], ["Command.update", "next_step / strategy_reason", "messages += Supervisor 决策消息"], 14, 2, FONT_SMALL, 16, "500"),
        ((1510, 500, 360, 120), COLORS["note_fill"], COLORS["note_stroke"], ["Command.update", "resume_text = optimized_resume", "optimization_round += 1", "shortlist = []", "revision_notes += revision_note"], 14, 2, FONT_SMALL, 16, "500"),
        ((1880, 390, 360, 120), COLORS["note_fill"], COLORS["note_stroke"], ["Command.update", "shortlist = Top 3(score >= 70)", "final_report = coach_report(...active_matches...)", "messages += 报告完成消息"], 14, 2, FONT_SMALL, 16, "500"),
        ((570, 995, 360, 110), COLORS["note_fill"], COLORS["note_stroke"], ["Command.update", "job_requirements =", "extract_job_requirements(...)", "goto position_job_node"], 14, 2, FONT_SMALL, 16, "500"),
        ((570, 1150, 320, 90), COLORS["note_fill"], COLORS["note_stroke"], ["return", "analyses += [JobAnalysis]"], 14, 2, FONT_SMALL, 16, "500"),
        ((1640, 995, 320, 90), COLORS["note_fill"], COLORS["note_stroke"], ["return", "match_result =", "score_match(...)"], 14, 2, FONT_SMALL, 16, "500"),
        ((1660, 1150, 400, 90), COLORS["note_fill"], COLORS["note_stroke"], ["return", "matches += [MatchResult(", "review_round = 当前 optimization_round)]"], 14, 2, FONT_SMALL, 16, "500"),

        ((120, 1490, 540, 110), COLORS["note_fill"], COLORS["note_stroke"], ["active_matches 只筛选", "review_round == optimization_round", "的当前轮匹配结果"], 18, 2, FONT_TEXT, 18, "500"),
        ((760, 1480, 760, 140), COLORS["note_fill"], COLORS["note_stroke"], ["低分回路触发条件", "high_count == 0", "AND average_score < 75", "AND optimization_round < max_optimization_rounds"], 18, 2, FONT_TEXT, 18, "500"),
        ((1600, 1470, 650, 160), COLORS["note_fill"], COLORS["note_stroke"], ["Supervisor 实际决策机制", "1. fallback 代码兜底", "2. 参考 LLM 决策", "3. 经过 _is_step_allowed 合法性校验"], 18, 2, FONT_TEXT, 18, "500"),
        ((120, 1640, 1020, 80), COLORS["note_fill"], COLORS["note_stroke"], ["正常链路: START -> supervisor -> Send(job_analysis_flow x N) -> supervisor -> Send(match_flow x N) -> supervisor -> career_coach -> supervisor -> finish_node -> END"], 18, 2, FONT_SMALL, 16, "500"),
        ((1170, 1640, 1080, 80), COLORS["note_fill"], COLORS["note_stroke"], ["低分回路链路: START -> supervisor -> Send(match_flow x N) 后若低分 -> resume_optimizer -> supervisor -> 再次 Send(match_flow x N) -> career_coach -> finish_node"], 18, 2, FONT_SMALL, 16, "500"),
    ]

    for rect, fill, stroke, lines, radius, stroke_width, font, font_size, font_weight in boxes:
        draw_box(draw, rect, fill, stroke, lines, radius=radius, width=stroke_width, font=font)
        svg_parts.append(
            svg_box(*rect, fill=fill, stroke=stroke, lines=lines, radius=radius, stroke_width=stroke_width, font_size=font_size, font_weight=font_weight)
        )

    draw_diamond(draw, (760, 390), (320, 160), ["Supervisor 决策后", "选择 goto"])
    svg_parts.append(svg_diamond(760, 390, 320, 160, ["Supervisor 决策后", "选择 goto"]))

    arrows = [
        ([(240, 220), (310, 220)], False),
        ([(560, 220), (610, 220)], False),
        ([(910, 220), (910, 390), (920, 390)], False),
        ([(920, 390), (1010, 210)], False),
        ([(920, 390), (1010, 390)], False),
        ([(920, 390), (1500, 190)], False),
        ([(920, 390), (1500, 380)], False),
        ([(920, 390), (1990, 280)], False),
        ([(2170, 280), (2190, 280)], False),
        ([(1665, 240), (1665, 500)], False),
        ([(1830, 380), (1880, 390)], False),
        ([(1500, 560), (1020, 560), (1020, 250), (435, 250)], False),
        ([(2240, 450), (2240, 700), (435, 700), (435, 270)], False),
        ([(1180, 270), (1180, 980), (370, 980)], False),
        ([(520, 1025), (570, 1025)], False),
        ([(930, 1050), (930, 1165), (520, 1165)], False),
        ([(520, 1280), (640, 1280)], False),
        ([(790, 1280), (790, 820), (435, 820), (435, 270)], False),
        ([(1190, 450), (1190, 980), (1430, 980)], False),
        ([(1580, 1025), (1640, 1025)], False),
        ([(1960, 1040), (1960, 1165), (1580, 1165)], False),
        ([(1620, 1280), (1780, 1280)], False),
        ([(2060, 1280), (2060, 840), (435, 840), (435, 270)], False),
        ([(390, 1600), (1190, 1600), (1190, 450)], True),
        ([(1030, 1620), (1665, 1620), (1665, 240)], True),
        ([(1930, 1630), (1830, 1630), (1830, 380)], True),
        ([(1920, 1550), (435, 1550), (435, 270)], True),
    ]

    for points, dashed in arrows:
        draw_arrow(draw, points, dashed=dashed)
        svg_parts.append(svg_arrow(points, dashed=dashed))

    footer = "文件来源: generate_project_graph_assets.py | 根目录资产: PROJECT_GRAPH.md / PROJECT_GRAPH.mmd / PROJECT_GRAPH.svg / PROJECT_GRAPH.png"
    draw.text((60, 1795), footer, font=FONT_SMALL, fill=COLORS["muted"])
    svg_parts.append(
        f'<text x="60" y="1818" font-size="16" fill="{COLORS["muted"]}" '
        f'font-family="PingFang SC, Helvetica, Arial, sans-serif">{escape(footer)}</text>'
    )

    svg_parts.append("</svg>")
    SVG_PATH.write_text("".join(svg_parts), encoding="utf-8")
    image.save(PNG_PATH)


if __name__ == "__main__":
    render()
