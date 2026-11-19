"""
cc5_uitab: list the tabs of a CC5 tab widget, or bring ONE tab to the front (/ui/tab), with a fake Qt.

What is checked: the listing (read-only, no job), selecting by index / text / tool tip, every refusal
(no or several tab widgets, no or several matching tabs, a disabled or hidden tab, the deny words, a
window that needs a person, a modal window), the job (setCurrentIndex on a Qt timer, picture after
wait_ms) and the arguments.

    python -m unittest discover -s tests/python -v      (or: npm run test:py)
"""

from __future__ import annotations

import json
import unittest

from ui_support import UiTestCase, cc5_ui, fake_qt

import cc5_uiclick  # noqa: E402
import cc5_uitab  # noqa: E402

TABS = [("", "Morph"), ("", "Texture"), ("", "Modify"), ("Motion", "")]


class TabTestCase(UiTestCase):
    """The main window with the Modify panel: one tab widget with icon-only tabs, and a button on a page."""

    def setUp(self) -> None:
        super().setUp()
        self.main = fake_qt.MainWindow(name="MainWindow", title="Character Creator 5 - test.ccProject")
        self.q.app.tops.append(self.main)
        self.panel = fake_qt.Widget(name="AttributeModify", parent=self.main)
        self.tabs = fake_qt.TabWidget(self.panel, name="qtAttributeRootTab", tabs=TABS)
        self.bar = fake_qt.TabBar(self.tabs, name="qt_tabwidget_tabbar", tabs=TABS)   # a tab widget's own bar
        self.tabs.pages = [fake_qt.Widget(name=f"qtPage{i}", parent=self.tabs) for i in range(len(TABS))]
        self.button = fake_qt.PushButton("Subdivide", self.tabs.pages[2], name="qtSubdivide", visible=False)

    def tab(self, **body):
        body.setdefault("window", "MainWindow")
        return cc5_uitab.ui_tab(body)

    def run_tab(self, **body):
        return self.finish(self.tab(**body))

    def assert_refused(self, res: dict, *needles: str) -> None:
        self.assertFalse(res["success"], res)
        for needle in needles:
            self.assertIn(needle, res["error"])
        self.assertEqual(fake_qt.Timer.singles, [], "a refused request must not start a job")
        self.assert_untouched()

    def assert_untouched(self) -> None:
        self.assertEqual((self.tabs.set_calls, self.bar.set_calls, self.button.clicks), ([], [], 0))


class ListingTest(TabTestCase):
    def test_list_only_returns_the_tab_widget_and_every_tab_and_changes_nothing(self) -> None:
        self.tabs.tab_enabled[3] = False
        self.tabs.tab_visible[1] = False
        res = self.tab(list_only=True)
        json.dumps(res)
        self.assertTrue(res["success"], res)
        self.assertTrue(res["listed"])
        self.assertNotIn("job_id", res)
        self.assertEqual(fake_qt.Timer.singles, [])
        self.assertEqual((res["window"], res["count"]), ("Character Creator 5 - test.ccProject", 1))
        holder = res["tab_widgets"][0]                       # the tab widget's own bar is not a second entry
        self.assertEqual((holder["object_name"], holder["class"], holder["current_index"], holder["count"]),
                         ("qtAttributeRootTab", "TabWidget", 0, 4))
        self.assertEqual(holder["tabs"][2], {"index": 2, "text": "", "tooltip": "Modify", "enabled": True,
                                             "visible": True, "page": "qtPage2"})
        self.assertEqual([(t["enabled"], t["visible"]) for t in holder["tabs"]],
                         [(True, True), (True, False), (True, True), (False, True)])
        self.assertEqual(self.main.grabbed, 0)
        self.assert_untouched()

    def test_no_selector_lists_and_list_only_wins_over_a_selector(self) -> None:
        for body in ({}, {"list_only": True, "index": 2}, {"tab_widget": "qtAttributeRootTab"}):
            with self.subTest(body=body):
                res = self.tab(**body)
                self.assertTrue(res["listed"], res)
                self.assertEqual(len(res["tab_widgets"]), 1)
        self.assert_untouched()

    def test_lists_several_tab_widgets_and_bare_tab_bars_but_not_hidden_ones(self) -> None:
        fake_qt.TabBar(self.panel, name="qtSubBar", tabs=[("A", ""), ("B", "")], current=1)
        fake_qt.TabWidget(self.panel, name="qtHiddenTab", tabs=[("X", "")], visible=False)
        res = self.tab()
        self.assertEqual([(h["object_name"], h["class"], h["current_index"]) for h in res["tab_widgets"]],
                         [("qtAttributeRootTab", "TabWidget", 0), ("qtSubBar", "TabBar", 1)])
        self.assertEqual(res["hidden_skipped"], 1)
        self.assertEqual(self.tab(tab_widget="qtSubBar")["count"], 1)
        self.assertEqual(self.tab(tab_widget="qtNope")["tab_widgets"], [])

    def test_tab_widgets_of_a_child_dialog_belong_to_that_dialog(self) -> None:
        child = fake_qt.Dialog(title="Options", parent=self.main)
        fake_qt.TabWidget(child, name="qtOptionTabs", tabs=[("General", "")])
        self.assertEqual([h["object_name"] for h in self.tab()["tab_widgets"]], ["qtAttributeRootTab"])

    def test_listing_works_while_a_window_needs_a_person(self) -> None:
        self.dialog("License", "Your license has expired", ["OK"])
        self.assertTrue(self.tab(list_only=True)["success"])

    def test_rich_text_and_shortcut_markers_are_cleaned_and_long_labels_are_cut(self) -> None:
        self.tabs._tabs[3] = ("&Motion", "<b>Motion</b> " + "x" * 400)
        tab = self.tab()["tab_widgets"][0]["tabs"][3]
        self.assertEqual(tab["text"], "Motion")
        self.assertTrue(tab["tooltip"].startswith("Motion x"))
        self.assertEqual(len(tab["tooltip"]), cc5_uitab.MAX_LABEL_CHARS)

    def test_a_qt_without_is_tab_visible_counts_tabs_as_visible(self) -> None:
        class OldTabWidget(fake_qt.TabWidget):
            isTabVisible = None                              # Qt before 5.15

        old = OldTabWidget(self.panel, name="qtOld", tabs=[("A", ""), ("B", "")])
        self.assertEqual([t["visible"] for t in self.tab(tab_widget="qtOld")["tab_widgets"][0]["tabs"]], [True, True])
        self.run_tab(tab_widget="qtOld", index=1)
        self.assertEqual(old.set_calls, [1])

    def test_unknown_window(self) -> None:
        self.assert_refused(self.tab(window="Headshot", list_only=True), "no open CC5 window")


class SelectingTest(TabTestCase):
    def test_by_index_reports_before_after_labels_picture_and_dialogs(self) -> None:
        result = self.run_tab(index=2)
        self.assertTrue(result["success"], result)
        self.assertEqual(self.tabs.set_calls, [2])
        self.assertEqual(self.bar.set_calls, [])
        self.assertEqual(result["tab_widget"], {"object_name": "qtAttributeRootTab", "class": "TabWidget"})
        self.assertEqual((result["index_before"], result["index_after"]), (0, 2))
        self.assertEqual((result["previous"]["tooltip"], result["selected"]["tooltip"]), ("Morph", "Modify"))
        self.assertEqual([t["index"] for t in result["tabs"]], [0, 1, 2, 3])
        self.assertTrue(result["select_returned"])
        self.assertTrue(result["window_open"])
        self.assertTrue(result["png_base64"])
        self.assertEqual(self.main.grabbed, 1)
        self.assertEqual(result["dialogs"], [])
        self.assertEqual(self.button.clicks, 0)              # nothing is ever pressed

    def test_by_tooltip_any_case_and_by_text_any_case_and_marker(self) -> None:
        self.run_tab(tooltip="  MODIFY ")
        self.assertEqual(self.tabs.currentIndex(), 2)
        self.run_tab(text="&motion")
        self.assertEqual(self.tabs.currentIndex(), 3)
        self.assertEqual(self.tabs.set_calls, [2, 3])

    def test_the_tab_that_is_already_in_front(self) -> None:
        result = self.run_tab(index=0)
        self.assertTrue(result["success"], result)
        self.assertEqual((result["index_before"], result["index_after"]), (0, 0))
        self.assertIn("already", result["note"])

    def test_a_dock_panel_and_a_bare_tab_bar(self) -> None:
        dock = fake_qt.DockWidget(name="qtModifyDock", title="Modify", parent=self.main)
        bar = fake_qt.TabBar(dock, name="qtDockBar", tabs=[("One", ""), ("Two", "")])
        result = self.run_tab(window="Modify", text="Two")
        self.assertEqual((bar.set_calls, result["index_after"], result["window"]), ([1], 1, "Modify"))
        self.assertEqual(result["tab_widget"]["class"], "TabBar")
        self.assertEqual(dock.grabbed, 1)
        self.assert_untouched()

    def test_tab_widget_picks_one_of_several(self) -> None:
        other = fake_qt.TabWidget(self.panel, name="qtSubTab", tabs=[("A", ""), ("B", "")])
        self.assert_refused(self.tab(index=1), "2 visible tab widgets", "[qtAttributeRootTab]", "[qtSubTab]",
                            "give tab_widget")
        self.run_tab(tab_widget="qtSubTab", index=1)
        self.assertEqual((other.set_calls, self.tabs.set_calls), ([1], []))

    def test_screenshot_false_returns_no_pictures(self) -> None:
        result = self.run_tab(index=1, screenshot=False)
        self.assertTrue(result["success"])
        self.assertNotIn("png_base64", result)
        self.assertEqual(self.main.grabbed, 0)


class RefusalTest(TabTestCase):
    def test_no_tab_widget_in_the_window(self) -> None:
        win = fake_qt.Dialog(title="Empty")
        self.q.app.tops.append(win)
        self.assert_refused(self.tab(window="Empty", index=0), "no visible tab widget")

    def test_unknown_or_hidden_or_duplicate_tab_widget_name(self) -> None:
        self.assert_refused(self.tab(tab_widget="qtNope", index=0), "no tab widget with objectName 'qtNope'",
                            "[qtAttributeRootTab]")
        hidden = fake_qt.TabWidget(self.panel, name="qtHiddenTab", tabs=[("X", ""), ("Y", "")], visible=False)
        self.assert_refused(self.tab(tab_widget="qtHiddenTab", index=1), "is hidden")
        self.assertEqual(hidden.set_calls, [])
        twins = [fake_qt.TabWidget(self.panel, name="qtTwin", tabs=[("X", ""), ("Y", "")]) for _ in range(2)]
        self.assert_refused(self.tab(tab_widget="qtTwin", index=1), "2 visible tab widgets", "share that objectName")
        self.assertEqual([t.set_calls for t in twins], [[], []])

    def test_a_tab_widgets_own_bar_cannot_be_named(self) -> None:
        self.assert_refused(self.tab(tab_widget="qt_tabwidget_tabbar", index=1), "no tab widget with objectName")

    def test_no_such_tab_lists_the_tabs(self) -> None:
        self.assert_refused(self.tab(index=9), "no tab with index 9", "2: (no text) tip 'Modify'", "3: 'Motion'")
        self.assert_refused(self.tab(text="Cloth"), "no tab with text 'Cloth'")
        self.assert_refused(self.tab(tooltip="Mod"), "no tab with tooltip 'Mod'")       # exact, not "contains"

    def test_several_matching_tabs_are_ambiguous(self) -> None:
        self.tabs._tabs[1] = ("", "Modify")
        self.assert_refused(self.tab(tooltip="modify"), "2 tabs match tooltip", "by its index")
        self.tabs._tabs[0] = ("Motion", "")
        self.assert_refused(self.tab(text="Motion"), "2 tabs match text")

    def test_disabled_and_hidden_tabs_and_a_disabled_tab_widget(self) -> None:
        self.tabs.tab_enabled[2] = False
        self.assert_refused(self.tab(index=2), "disabled")
        self.tabs.tab_enabled[2] = True
        self.tabs.tab_visible[2] = False
        self.assert_refused(self.tab(tooltip="Modify"), "is hidden")
        self.tabs.tab_visible[2] = True
        self.tabs._enabled = False
        self.assert_refused(self.tab(index=2), "disabled")

    def test_deny_words_in_the_text_or_the_tool_tip(self) -> None:
        cases = (("Buy Content", ""), ("", "Purchase more"), ("License", ""), ("", "<b>Del</b>ete layers"),
                 ("AI Points", ""), ("Log In", ""), ("", "Upgrade"), ("", "x" * 300 + " subscribe"))
        for text, tip in cases:
            with self.subTest(text=text, tip=tip):
                self.tabs._tabs[1] = (text, tip)
                self.assert_refused(self.tab(index=1), "refused", "mentions")
        self.assertEqual(cc5_uiclick.deny_reason("Modify", "Texture"), None)

    def test_nothing_is_selected_while_a_window_needs_a_person(self) -> None:
        self.dialog("License", "Your license has expired", ["OK"])
        self.assert_refused(self.tab(index=2), "a person must decide")

    def test_a_modal_window_blocks_tab_widgets_outside_it_but_not_inside(self) -> None:
        dlg = self.dialog("Export Settings", "Choose", ["OK", "Cancel"])
        dlg._modal = True
        inside = fake_qt.TabWidget(dlg, name="qtExportTabs", tabs=[("Mesh", ""), ("Motion", "")])
        self.assert_refused(self.tab(index=2), "modal window 'Export Settings' is open")
        result = self.run_tab(window="Export Settings", text="Motion")
        self.assertTrue(result["success"], result)
        self.assertEqual(inside.set_calls, [1])
        self.assertEqual([b.clicks for b in dlg.findChildren(fake_qt.PushButton)], [0, 0])
        self.assertEqual(self.tabs.set_calls, [])


class JobTest(TabTestCase):
    def test_the_switch_runs_on_a_qt_timer_and_the_picture_comes_after_wait_ms(self) -> None:
        started = self.tab(index=2, wait_ms=2500)
        self.assertTrue(started["success"], started)
        self.assertTrue(started["job_id"].startswith("tab-"))
        fake_qt.drain(1)                                     # the job's first step: schedules the switch
        self.assertEqual(fake_qt.Timer.pending_ms(), [cc5_uitab.SELECT_DELAY_MS, cc5_uitab.SELECT_DELAY_MS + 2500])
        self.assertEqual(self.tabs.set_calls, [])
        result = self.finish(started)
        self.assertEqual((self.tabs.set_calls, result["waited_ms"]), ([2], 2500))

    def test_the_tab_is_checked_again_when_the_job_starts(self) -> None:
        started = self.tab(index=2)
        self.tabs.tab_enabled[2] = False                     # greyed out before the job's first step
        result = self.finish(started)
        self.assertFalse(result["success"])
        self.assertIn("disabled", result["error"])
        self.assertEqual(self.tabs.set_calls, [])

    def test_a_switch_that_raises_or_does_not_take_is_reported(self) -> None:
        def boom(_index: int) -> None:
            raise RuntimeError("Internal C++ object already deleted")

        self.tabs.on_change = boom
        result = self.run_tab(index=1)
        self.assertFalse(result["success"])
        self.assertIn("RuntimeError", result["error"])
        self.tabs.on_change = lambda _index: setattr(self.tabs, "_current", 0)       # CC5 switches back
        result = self.run_tab(index=3)
        self.assertFalse(result["success"])
        self.assertIn("the current tab is 0", result["error"])

    def test_a_window_the_switch_opened_is_reported_and_not_answered(self) -> None:
        opened = []
        self.tabs.on_change = lambda _index: opened.append(self.dialog("Note", "Loading the page.", ["OK"]))
        result = self.run_tab(index=2)
        self.assertTrue(result["success"], result)
        self.assertEqual([d["title"] for d in result["dialogs"]], ["Note"])
        self.assertEqual([b.clicks for b in opened[0].findChildren(fake_qt.PushButton)], [0])

    def test_one_ui_job_at_a_time(self) -> None:
        cc5_ui.start_job("other", lambda p: {"success": True}, {})
        res = self.tab(index=2)
        self.assertFalse(res["success"])
        self.assertIn("another UI job", res["error"])


class ArgumentsTest(TabTestCase):
    def test_bad_requests_are_refused_before_anything_runs(self) -> None:
        bad = (
            {},
            {"index": 1},
            {"window": "", "index": 1},
            {"window": 3, "index": 1},
            {"window": "MainWindow", "index": -1},
            {"window": "MainWindow", "index": 1000},
            {"window": "MainWindow", "index": "2"},
            {"window": "MainWindow", "index": 1.5},
            {"window": "MainWindow", "index": True},
            {"window": "MainWindow", "text": ""},
            {"window": "MainWindow", "tooltip": "x" * 300},
            {"window": "MainWindow", "tab_widget": "x" * 300, "index": 1},
            {"window": "MainWindow", "index": 1, "text": "Motion"},
            {"window": "MainWindow", "text": "Motion", "tooltip": "Modify"},
            {"window": "MainWindow", "index": 1, "tabwidget": "qtAttributeRootTab"},
            {"window": "MainWindow", "index": 1, "object_name": "qtSubdivide"},
            {"window": "MainWindow", "index": 1, "menu_item": "Save"},
            {"window": "MainWindow", "index": 1, "screenshot": "yes"},
            {"window": "MainWindow", "index": 1, "list_only": "no"},
        )
        for body in bad:
            with self.subTest(body=body):
                self.assertFalse(cc5_uitab.ui_tab(body)["success"])
        self.assertEqual(fake_qt.Timer.singles, [])
        self.assert_untouched()

    def test_wait_ms_default_and_limits(self) -> None:
        def wait(value: object = None) -> int:
            body = {"window": "w", "index": 0}
            if value is not None:
                body["wait_ms"] = value
            return cc5_uitab.read_args(body)[0]["wait_ms"]

        self.assertEqual(wait(), cc5_uitab.DEFAULT_WAIT_MS)
        self.assertEqual(wait(999_999), cc5_uitab.MAX_WAIT_MS)
        self.assertEqual(wait(1), cc5_uitab.MIN_WAIT_MS)
        self.assertEqual(wait("nope"), cc5_uitab.DEFAULT_WAIT_MS)

    def test_route(self) -> None:
        self.assertEqual(cc5_uitab.ROUTES, {"/ui/tab": ("ui_tab", cc5_uitab.ui_tab)})


if __name__ == "__main__":
    unittest.main()
