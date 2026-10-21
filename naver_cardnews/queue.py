"""엑셀 뉴스 큐: DB → 엑셀 내보내기(매 실행 재생성), 엑셀 → DB 승인 값 읽어오기."""

from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .db import STATUSES, Database

KST = timezone(timedelta(hours=9))
SHEET = "뉴스큐"

# (헤더, 너비, DB 컬럼 또는 None)
COLUMNS = [
    ("id", 14, "id"),
    ("수집일시", 17, "collected_at"),
    ("키워드", 16, "keywords_hit"),
    ("제목", 55, "title"),
    ("언론사", 18, "press"),
    ("발행일시", 17, "pub_date"),
    ("naver_link", 40, "naver_link"),
    ("originallink", 40, "originallink"),
    ("요약", 70, "description"),
    ("정규화제목", 30, "title_key"),
    ("cluster_id", 10, "cluster_id"),
    ("대표여부", 9, "is_representative"),
    ("중복사유", 36, "dup_reason"),
    ("점수", 7, "score"),
    ("상태", 10, "status"),
    ("카드폴더", 20, "card_folder"),
    ("게시URL", 30, "post_url"),
    ("메모", 30, "memo"),
]
EDITABLE = {"상태": "status", "카드폴더": "card_folder", "게시URL": "post_url", "메모": "memo"}


class ExcelLocked(RuntimeError):
    pass


def _kst(iso: str | None) -> str:
    if not iso:
        return ""
    return datetime.fromisoformat(iso).astimezone(KST).strftime("%Y-%m-%d %H:%M")


def _check_lock(path: Path) -> None:
    lock = path.with_name(f"~${path.name}")
    if lock.exists():
        raise ExcelLocked(f"{path.name} 이(가) 엑셀에서 열려 있습니다 ({lock.name}). 닫고 다시 실행하세요.")


def _backup(path: Path, keep: int = 10) -> Path | None:
    if not path.exists():
        return None
    bdir = path.parent / "backups"
    bdir.mkdir(exist_ok=True)
    dest = bdir / f"{path.stem}_{datetime.now(KST).strftime('%Y%m%d_%H%M%S')}{path.suffix}"
    shutil.copy2(path, dest)
    for old in sorted(bdir.glob(f"{path.stem}_*{path.suffix}"))[:-keep]:
        old.unlink()
    return dest


def export_queue(db: Database, output: Path) -> int:
    """DB 전체를 엑셀로 재생성. 기존 파일은 backups/에 백업."""
    _check_lock(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = db.for_export()

    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    head_font, head_fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1F4E78")
    edit_fill = PatternFill("solid", fgColor="FFF2CC")
    for c, (name, width, _) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=c, value=name)
        cell.font, cell.fill = head_font, head_fill
        if name in EDITABLE:
            cell.fill = PatternFill("solid", fgColor="BF8F00")
        ws.column_dimensions[get_column_letter(c)].width = width
    ws.freeze_panes = "E2"

    for r, row in enumerate(rows, start=2):
        for c, (name, _, col) in enumerate(COLUMNS, start=1):
            value = row[col]
            if col in ("collected_at", "pub_date"):
                value = _kst(value)
            elif col == "is_representative":
                value = "대표" if value else ""
            cell = ws.cell(row=r, column=c, value=value)
            if name in EDITABLE:
                cell.fill = edit_fill
            if col in ("naver_link", "originallink") and value:
                cell.hyperlink = value
                cell.font = Font(color="0563C1", underline="single")
            if col in ("title", "description"):
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        if row["status"] == "제외":
            for c in range(1, len(COLUMNS) + 1):
                ws.cell(row=r, column=c).font = Font(color="999999")

    if rows:
        status_col = get_column_letter([n for n, _, _ in COLUMNS].index("상태") + 1)
        dv = DataValidation(type="list", formula1='"' + ",".join(STATUSES) + '"', allow_blank=False)
        ws.add_data_validation(dv)
        dv.add(f"{status_col}2:{status_col}{len(rows) + 1}")
        ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{len(rows) + 1}"

    meta = wb.create_sheet("요약")
    meta.append(["생성 시각(KST)", datetime.now(KST).strftime("%Y-%m-%d %H:%M")])
    for k, v in db.stats().items():
        meta.append([k, v])
    meta.append([])
    meta.append(["사용법", "상태를 '승인'으로 바꾸고 저장 → 다음 실행 때 DB로 반영됩니다. 노란 열만 편집하세요."])
    meta.column_dimensions["A"].width = 16

    _backup(output)
    wb.save(output)
    return len(rows)


def import_queue(db: Database, path: Path) -> int:
    """엑셀의 편집 가능 열(상태·카드폴더·게시URL·메모)을 DB로 읽어온다. 바뀐 행 수를 돌려준다."""
    if not path.exists():
        return 0
    _check_lock(path)
    wb = load_workbook(path, read_only=True, data_only=True)
    if SHEET not in wb.sheetnames:
        return 0
    ws = wb[SHEET]
    rows = ws.iter_rows(values_only=True)
    header = [str(h) if h is not None else "" for h in next(rows, [])]
    if "id" not in header:
        return 0
    idx = {name: header.index(name) for name in ["id", *EDITABLE] if name in header}
    changed = 0
    with db.transaction():
        for row in rows:
            if not row or row[idx["id"]] is None:
                continue
            article_id = str(row[idx["id"]]).strip()

            def val(name: str) -> str | None:
                if name not in idx:
                    return None
                v = row[idx[name]]
                return "" if v is None else str(v).strip()

            if db.update_review(article_id, val("상태"), val("메모"), val("카드폴더"), val("게시URL")):
                changed += 1
    wb.close()
    return changed
