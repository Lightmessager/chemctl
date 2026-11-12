"""Focused checks for issues found in the frontend handoff; no network or SSH."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from chemctl.gui import Window
from chemctl.parsing import parse_output


def test_unrecognized_output_has_detail_fields(tmp_path):
    path = tmp_path / "runner.log"
    path.write_text("This is a launcher log, not a chemistry calculation.\n")
    result = parse_output(path)
    assert result["status"] == "unsupported"
    assert result["calculation_status"] is None
    assert result["frequency_summary"] is None


def test_result_changes_clear_export_and_refresh_same_record(monkeypatch):
    app = QApplication.instance() or QApplication([])
    requests = []
    monkeypatch.setattr(Window, "request", lambda self, fn, callback, on_error=None, busy=None: requests.append((callback, on_error)))
    window = Window()
    try:
        window.structure = {"source_location": {"path": "old.out"}}
        window.xyz.setPlainText("old structure")
        for tool in window.structure_tools:
            tool.setEnabled(True)
        window.load_calc("new")
        assert window.structure is None
        assert window.xyz.toPlainText() == ""
        assert all(not tool.isEnabled() for tool in window.structure_tools)

        stale_replies = []
        old_callback = window.for_calc(stale_replies.append)
        window.load_calc("new")
        old_callback("old reply for the same calculation")
        assert stale_replies == []
        requests[-2][1]("STALE_RESULT")  # structure request failed
        assert all(not tool.isEnabled() for tool in window.structure_tools)

        record = {"calculation_id": "new", "title": "new.out", "engine": "orca", "method": None,
                  "basis_set": None, "status": "partial", "calculation_status": "incomplete",
                  "final_energy_eh": None, "frequency_summary": None}
        window.results.fill({"items": [record], "total": 1, "offset": 0}, window.result_cells)
        window.results.select("calculation_id", "new")
        loaded = []
        monkeypatch.setattr(window, "load_calc", lambda key: loaded.append(key))
        window.refresh_results()
        requests[-1][0]({"items": [record], "total": 1, "offset": 0})
        assert loaded == ["new"]
        window.refresh_results()
        previous_list = requests[-1][0]
        window.refresh_results()
        requests[-1][0]({"items": [], "total": 0, "offset": 0})
        previous_list({"items": [record], "total": 1, "offset": 0})
        assert window.calc_id is None
        assert window.results.table.rowCount() == 0
    finally:
        window.close()
