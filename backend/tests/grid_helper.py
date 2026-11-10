"""測試用：把 xlsx 轉成與 Sheets API 解析結果相同的 Grid。"""
import openpyxl

from app.sheets.parser import Grid


def _fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def xlsx_to_grid(path) -> tuple[Grid, str]:
    wb = openpyxl.load_workbook(path)
    ws = wb.worksheets[0]
    rows = [
        [_fmt(ws.cell(row=r, column=c).value) for c in range(1, ws.max_column + 1)]
        for r in range(1, ws.max_row + 1)
    ]
    merges = [
        (m.min_row - 1, m.max_row, m.min_col - 1, m.max_col) for m in ws.merged_cells.ranges
    ]
    return Grid(rows=rows, merges=merges), ws.title
