"""
cc5_uivalue: read ONE input widget of a CC5 window, or set its value (/ui/value), with a fake Qt.

What is checked: the reading (read-only, no job), finding the widget by objectName and ancestor, every
kind (spin box, double spin box, a custom spin box reached through Qt properties, slider, combo box,
line edit, check box, radio button), every refusal (no match, ambiguous, hidden, disabled, wrong type,
out of range, the deny words, the allowlist, a window that needs a person, a modal window), the job
(the change on a Qt timer, picture after wait_ms) and the arguments.

    python -m unittest discover -s tests/python -v      (or: npm run test:py)
"""

from __future__ import annotations

import json
import unittest

from ui_support import UiTestCase, cc5_ui, fake_qt

import cc5_uiclick  # noqa: E402
import cc5_uivalue  # noqa: E402


class ValueTestCase(UiTestCase):
    """The main window with the Modify panel: the two SubD spin boxes that share an objectName, a slider,
    a combo box, a line edit, the wrinkle check box and a push button."""

    def setUp(self) -> None:
        super().setUp()
        self.main = fake_qt.MainWindow(name="MainWindow", title="Character Creator 5 - test.ccProject")
        self.q.app.tops.append(self.main)
        self.panel = fake_qt.Widget(name="AttributeModify", parent=self.main)
        self.render_box = fake_qt.Widget(name="qtRenderComboSpinBox", parent=self.panel)
        self.preview_box = fake_qt.Widget(name="qtPreviewComboSpinBox", parent=self.panel)
        self.render = fake_qt.SpinBox(self.render_box, name="qtSpinBox", value=0, lo=0, hi=2)
        self.preview = fake_qt.SpinBox(self.preview_box, name="qtSpinBox", value=1, lo=0, hi=2)
        self.slider = fake_qt.Slider(self.panel, name="qtOpacitySlider", value=10, lo=0, hi=100)
        self.double = fake_qt.DoubleSpinBox(self.panel, name="qtWeight", value=0.25, lo=0.0, hi=1.0, decimals=2)
        self.combo = fake_qt.ComboBox(self.panel, name="qtMaterialCombo", items=["Head", "Body", "Arm", "arm"])
        self.line = fake_qt.LineEdit(self.panel, text="12.5", name="qtHeightEdit")
        self.wrinkle = fake_qt.CheckBox("Activate Expression Wrinkles", self.panel, name="qtActiveWrinkleCheckBox")
        self.wrinkle.auto_toggle = True
        self.button = fake_qt.PushButton("Subdivide", self.panel, name="qtSubdivide")

    def value(self, **body):
        body.setdefault("window", "MainWindow")
        return cc5_uivalue.ui_value(body)

    def run_value(self, **body):
        return self.finish(self.value(**body))

    def assert_refused(self, res: dict, *needles: str) -> None:
        self.assertFalse(res["success"], res)
        for needle in needles:
            self.assertIn(needle, res["error"])
        self.assertEqual(fake_qt.Timer.singles, [], "a refused request must not start a job")
        self.assert_untouched()

    def assert_untouched(self) -> None:
        self.assertEqual((self.render.set_calls, self.preview.set_calls, self.slider.calls, self.double.set_calls,
                          self.combo.set_calls, self.line.set_calls, self.wrinkle.clicks, self.button.clicks),
                         ([], [], [], [], [], [], 0, 0))


class ReadingTest(ValueTestCase):
    def test_read_only_reports_kind_value_range_and_changes_nothing(self) -> None:
        res = self.value(object_name="qtSpinBox", ancestor="qtRenderComboSpinBox", read_only=True)
        json.dumps(res)
        self.assertTrue(res["success"], res)
        self.assertTrue(res["read_only"])
        self.assertNotIn("job_id", res)
        self.assertEqual(fake_qt.Timer.singles, [])
        widget = res["widget"]
        self.assertEqual((widget["kind"], widget["value"], widget["minimum"], widget["maximum"], widget["single_step"]),
                         ("int", 0, 0, 2, 1))
        self.assertEqual((widget["object_name"], widget["class"], widget["enabled"]), ("qtSpinBox", "SpinBox", True))
        self.assertTrue(widget["path"].startswith("qtRenderComboSpinBox < AttributeModify < MainWindow"))
        self.assertEqual(self.main.grabbed, 0)
        self.assert_untouched()

    def test_read_only_wins_over_a_value(self) -> None:
        res = self.value(object_name="qtOpacitySlider", read_only=True, value=50)
        self.assertEqual((res["widget"]["kind"], res["widget"]["value"]), ("slider", 10))
        self.assert_untouched()

    def test_every_kind_is_described(self) -> None:
        double = self.value(object_name="qtWeight", read_only=True)["widget"]
        self.assertEqual((double["kind"], double["value"], double["minimum"], double["maximum"], double["decimals"]),
                         ("double", 0.25, 0.0, 1.0, 2))
        combo = self.value(object_name="qtMaterialCombo", read_only=True)["widget"]
        self.assertEqual((combo["kind"], combo["value"], combo["items"], combo["count"], combo["editable"]),
                         ("combo", {"index": 0, "text": "Head"}, ["Head", "Body", "Arm", "arm"], 4, False))
        check = self.value(object_name="qtActiveWrinkleCheckBox", read_only=True)["widget"]
        self.assertEqual((check["kind"], check["value"], check["text"]), ("check", False, "Activate Expression Wrinkles"))
        line = self.value(object_name="qtHeightEdit", read_only=True)["widget"]
        self.assertEqual((line["kind"], line["value"], line["read_only"]), ("text", "12.5", False))

    def test_typed_text_that_is_not_a_number_is_never_returned(self) -> None:
        self.line._text = "me@example.com"
        widget = self.value(object_name="qtHeightEdit", read_only=True)["widget"]
        self.assertIsNone(widget["value"])
        self.assertEqual((widget["value_hidden"], widget["text_length"]), (True, 14))
        self.assertNotIn("example", json.dumps(widget))

    def test_a_password_box_is_neither_read_nor_set(self) -> None:
        fake_qt.LineEdit(self.panel, text="hunter2", echo=fake_qt.LineEdit.Password, name="qtPassword")
        for body in ({"read_only": True}, {"value": "x"}):
            res = self.value(object_name="qtPassword", **body)
            self.assert_refused(res, "password box")
            self.assertNotIn("hunter2", json.dumps(res))

    def test_labels_and_tool_tip_are_reported(self) -> None:
        fake_qt.Label("Render", self.render_box)
        self.render._tooltip = "<b>Render</b> subdivision level"
        widget = self.value(object_name="qtSpinBox", ancestor="qtRenderComboSpinBox", read_only=True)["widget"]
        self.assertEqual((widget["labels"], widget["tooltip"]), (["Render"], "Render subdivision level"))

    def test_reading_works_while_a_window_needs_a_person_and_for_a_money_widget(self) -> None:
        self.dialog("License", "Your license has expired", ["OK"])
        fake_qt.SpinBox(self.panel, name="qtBuyCount", value=3)
        self.assertTrue(self.value(object_name="qtOpacitySlider", read_only=True)["success"])
        self.assertEqual(self.value(object_name="qtBuyCount", read_only=True)["widget"]["value"], 3)

    def test_unknown_window(self) -> None:
        self.assert_refused(self.value(window="Headshot", object_name="qtSpinBox", read_only=True), "no open CC5 window")


class FindingTest(ValueTestCase):
    def test_two_widgets_with_one_name_are_ambiguous_until_the_ancestor_picks_one(self) -> None:
        res = self.value(object_name="qtSpinBox", value=2)
        self.assert_refused(res, "2 visible input widgets match objectName 'qtSpinBox'", "qtRenderComboSpinBox",
                            "qtPreviewComboSpinBox", "give ancestor")
        result = self.run_value(object_name="qtSpinBox", ancestor="qtRenderComboSpinBox", value=2)
        self.assertTrue(result["success"], result)
        self.assertEqual((self.render.value(), self.preview.value(), self.preview.set_calls), (2, 1, []))

    def test_ancestor_may_be_a_class_or_any_widget_above_and_must_match(self) -> None:
        self.assert_refused(self.value(object_name="qtSpinBox", ancestor="AttributeModify", value=2), "2 visible input widgets")
        self.assert_refused(self.value(object_name="qtSpinBox", ancestor="qtNope", value=2),
                            "no widget with objectName 'qtSpinBox' under 'qtNope'")
        self.assert_refused(self.value(object_name="qtSpinBox", ancestor="qtSpinBox", value=2), "no widget")  # not itself
        self.assertEqual(self.value(object_name="qtOpacitySlider", ancestor="mainwindow", read_only=True)["widget"]["value"], 10)

    def test_no_such_widget_and_a_widget_that_is_no_input(self) -> None:
        self.assert_refused(self.value(object_name="qtNope", value=1), "no widget with objectName 'qtNope'", "find_ui_widgets")
        self.assert_refused(self.value(object_name="qtSubdivide", value=True), "not an input", "click_ui_button")
        self.assert_refused(self.value(object_name="AttributeModify", value=1), "not an input", "spin boxes")

    def test_hidden_widgets_never_count_and_are_never_changed(self) -> None:
        ghost = fake_qt.SpinBox(self.render_box, name="qtSpinBox", value=0, lo=0, hi=2, visible=False)
        result = self.run_value(object_name="qtSpinBox", ancestor="qtRenderComboSpinBox", value=1)
        self.assertEqual((self.render.value(), ghost.set_calls, result["hidden_skipped"]), (1, [], 1))
        only_hidden = fake_qt.SpinBox(self.panel, name="qtHiddenSpin", visible=False)
        self.render.set_calls.clear()
        self.assert_refused(self.value(object_name="qtHiddenSpin", value=1), "is hidden", "select_ui_tab")
        self.assertEqual(only_hidden.set_calls, [])

    def test_widgets_of_a_child_dialog_belong_to_that_dialog(self) -> None:
        child = fake_qt.Dialog(title="Options", parent=self.main)
        inner = fake_qt.SpinBox(child, name="qtOptionSpin", value=1)
        self.assert_refused(self.value(object_name="qtOptionSpin", value=2), "no widget")
        self.assertEqual(inner.set_calls, [])

    def test_a_dock_panel_can_be_the_window(self) -> None:
        dock = fake_qt.DockWidget(name="qtModifyDock", title="Modify", parent=self.main)
        spin = fake_qt.SpinBox(dock, name="qtDockSpin", value=1, lo=0, hi=5)
        result = self.run_value(window="Modify", object_name="qtDockSpin", value=4)
        self.assertEqual((spin.value(), result["window"], dock.grabbed), (4, "Modify", 1))

    def test_the_inner_text_box_of_a_spin_box_is_refused(self) -> None:
        fake_qt.LineEdit(self.render, text="0", name="qt_spinbox_lineedit")
        self.assert_refused(self.value(object_name="qt_spinbox_lineedit", value="2"), "inner text box", "[qtSpinBox]")


class SettingTest(ValueTestCase):
    def test_spin_box_reports_before_after_picture_and_dialogs(self) -> None:
        seen = []
        self.render.editingFinished.connect(lambda: seen.append(self.render.value()))
        result = self.run_value(object_name="qtSpinBox", ancestor="qtRenderComboSpinBox", value=2)
        self.assertTrue(result["success"], result)
        self.assertEqual((result["value_before"], result["value_after"], result["requested"], result["changed"]),
                         (0, 2, 2, True))
        self.assertEqual((result["minimum"], result["maximum"]), (0, 2))
        self.assertEqual(result["widget"]["kind"], "int")
        self.assertEqual((self.render.set_calls, seen, result["signals_sent"]), ([2], [2], ["editingFinished"]))
        self.assertTrue(result["set_returned"])
        self.assertTrue(result["window_open"])
        self.assertTrue(result["png_base64"])
        self.assertEqual(self.main.grabbed, 1)
        self.assertEqual(result["dialogs"], [])
        self.assertEqual(self.button.clicks, 0)              # nothing is ever pressed

    def test_a_whole_number_given_as_a_float_is_taken_and_a_fraction_is_not(self) -> None:
        self.run_value(object_name="qtSpinBox", ancestor="qtRenderComboSpinBox", value=2.0)
        self.assertEqual(self.render.set_calls, [2])
        self.render.set_calls.clear()
        self.assert_refused(self.value(object_name="qtSpinBox", ancestor="qtRenderComboSpinBox", value=1.5),
                            "whole numbers only")

    def test_out_of_range_is_refused_with_the_range_and_nothing_is_clamped(self) -> None:
        for name, ancestor, value, needle in (("qtSpinBox", "qtRenderComboSpinBox", 3, "minimum 0, maximum 2"),
                                              ("qtSpinBox", "qtRenderComboSpinBox", -1, "minimum 0, maximum 2"),
                                              ("qtOpacitySlider", None, 101, "minimum 0, maximum 100"),
                                              ("qtWeight", None, 1.01, "minimum 0.0, maximum 1.0")):
            with self.subTest(name=name, value=value):
                body = {"object_name": name, "value": value}
                if ancestor:
                    body["ancestor"] = ancestor
                self.assert_refused(self.value(**body), "outside the range", needle, "never clamped")

    def test_wrong_value_types_are_refused(self) -> None:
        cases = (("qtOpacitySlider", "50", "must be a number"), ("qtOpacitySlider", True, "must be a number"),
                 ("qtWeight", "0.5", "must be a number"), ("qtActiveWrinkleCheckBox", 1, "true or false"),
                 ("qtActiveWrinkleCheckBox", "true", "true or false"), ("qtHeightEdit", 12, "must be a string"),
                 ("qtMaterialCombo", True, "item text"))
        for name, value, needle in cases:
            with self.subTest(name=name, value=value):
                self.assert_refused(self.value(object_name=name, value=value), needle)

    def test_double_spin_box_and_its_rounding_note(self) -> None:
        result = self.run_value(object_name="qtWeight", value=0.5)
        self.assertEqual((result["value_before"], result["value_after"], self.double.set_calls), (0.25, 0.5, [0.5]))
        self.assertNotIn("note", result)
        result = self.run_value(object_name="qtWeight", value=0.333)
        self.assertTrue(result["success"], result)
        self.assertEqual(result["value_after"], 0.33)
        self.assertIn("2 decimal(s)", result["note"])

    def test_a_custom_spin_box_is_set_through_its_qt_properties(self) -> None:
        custom = fake_qt.AbstractSpinBox(self.panel, name="qtCustomSpin")
        custom._props.update({"value": 1.0, "minimum": 0.0, "maximum": 4.0})
        widget = self.value(object_name="qtCustomSpin", read_only=True)["widget"]
        self.assertEqual((widget["kind"], widget["value"], widget["maximum"]), ("spin", 1.0, 4.0))
        self.assert_refused(self.value(object_name="qtCustomSpin", value=5), "outside the range")
        result = self.run_value(object_name="qtCustomSpin", value=3)
        self.assertTrue(result["success"], result)
        self.assertEqual((custom._props["value"], result["value_after"]), (3.0, 3.0))
        fake_qt.AbstractSpinBox(self.panel, name="qtDateEdit")       # no numeric value property: not an input
        self.assertIn("not an input", self.value(object_name="qtDateEdit", read_only=True)["error"])

    def test_slider_is_dragged_and_one_without_those_methods_gets_set_value(self) -> None:
        result = self.run_value(object_name="qtOpacitySlider", value=75)
        self.assertTrue(result["success"], result)
        self.assertEqual(self.slider.calls, [("down", True), ("position", 75), ("down", False)])
        self.assertEqual((result["value_before"], result["value_after"]), (10, 75))

        class Dial(fake_qt.Slider):
            setSliderDown = None

        dial = Dial(self.panel, name="qtDial", value=1, lo=0, hi=10)
        self.run_value(object_name="qtDial", value=7)
        self.assertEqual(dial.calls, [("setValue", 7)])

    def test_combo_by_exact_text_by_loose_text_and_by_index(self) -> None:
        activated, texts = [], []
        self.combo.activated.connect(activated.append)
        self.combo.textActivated.connect(texts.append)
        result = self.run_value(object_name="qtMaterialCombo", value="Body")
        self.assertTrue(result["success"], result)
        self.assertEqual((result["value_before"], result["value_after"]),
                         ({"index": 0, "text": "Head"}, {"index": 1, "text": "Body"}))
        self.assertEqual(result["signals_sent"], ["activated", "textActivated"])
        self.run_value(object_name="qtMaterialCombo", value="arm")           # the exact text wins over "Arm"
        self.run_value(object_name="qtMaterialCombo", value="  HEAD ")
        self.run_value(object_name="qtMaterialCombo", value=2)
        self.assertEqual((self.combo.set_calls, activated, texts), ([1, 3, 0, 2], [1, 3, 0, 2], ["Body", "arm", "Head", "Arm"]))

    def test_combo_refusals(self) -> None:
        self.assert_refused(self.value(object_name="qtMaterialCombo", value="Leg"), "no item 'Leg'", "0: 'Head'")
        self.assert_refused(self.value(object_name="qtMaterialCombo", value="ARM"), "2 items", "give the index")
        self.assert_refused(self.value(object_name="qtMaterialCombo", value=4), "no item with index 4")
        self.assert_refused(self.value(object_name="qtMaterialCombo", value=-1), "no item with index -1")
        self.assert_refused(self.value(object_name="qtMaterialCombo", value=1.5), "no item with index 1.5")
        self.combo._items.append("Buy more materials...")
        self.assert_refused(self.value(object_name="qtMaterialCombo", value=4), "refused", "the item", "mentions 'buy'")
        self.combo.model = lambda: type("M", (), {"item": lambda _s, i: type("I", (), {"isEnabled": lambda _s: i != 1})()})()
        self.assert_refused(self.value(object_name="qtMaterialCombo", value="Body"), "disabled")

    def test_line_edit_text_and_signals_and_the_old_text_is_not_returned(self) -> None:
        edited, finished = [], []
        self.line.textEdited.connect(edited.append)
        self.line.editingFinished.connect(lambda: finished.append(self.line.text()))
        self.line._text = "old secret"
        result = self.run_value(object_name="qtHeightEdit", value="180")
        self.assertTrue(result["success"], result)
        self.assertIsNone(result["value_before"])
        self.assertTrue(result["value_before_hidden"])
        self.assertEqual((result["value_after"], self.line.text(), edited, finished), ("180", "180", ["180"], ["180"]))
        self.assertEqual(result["signals_sent"], ["textEdited", "editingFinished"])
        self.assertNotIn("old secret", json.dumps(result))

    def test_line_edit_refusals_and_a_validator_that_says_no(self) -> None:
        self.line._max_length = 4
        self.assert_refused(self.value(object_name="qtHeightEdit", value="12345"), "at most 4 characters")
        self.line._read_only = True
        self.assert_refused(self.value(object_name="qtHeightEdit", value="1"), "read-only")
        self.line._read_only = False
        self.line.accepts = lambda text: text.replace(".", "").isdigit()
        finished = []
        self.line.editingFinished.connect(lambda: finished.append(1))
        result = self.run_value(object_name="qtHeightEdit", value="abc")
        self.assertFalse(result["success"])
        self.assertIn("does not accept that text", result["error"])
        self.assertEqual((self.line.text(), self.line.set_calls, finished), ("12.5", ["abc", "12.5"], []))

    def test_check_box_is_clicked_only_when_the_state_differs(self) -> None:
        result = self.run_value(object_name="qtActiveWrinkleCheckBox", value=True)
        self.assertTrue(result["success"], result)
        self.assertEqual((result["value_before"], result["value_after"], self.wrinkle.clicks), (False, True, 1))
        result = self.run_value(object_name="qtActiveWrinkleCheckBox", value=True)
        self.assertTrue(result["success"], result)
        self.assertIn("already had that value", result["note"])
        self.assertEqual((self.wrinkle.clicks, result["changed"]), (1, False))
        self.run_value(object_name="qtActiveWrinkleCheckBox", value=False)
        self.assertEqual((self.wrinkle.clicks, self.wrinkle.isChecked()), (2, False))

    def test_a_tristate_box_gets_set_checked_and_a_radio_button_that_stays_on_is_reported(self) -> None:
        tri = fake_qt.CheckBox("Mirror", self.panel, name="qtMirror")
        tri.isTristate = lambda: True
        self.run_value(object_name="qtMirror", value=True)
        self.assertEqual((tri.clicks, tri.isChecked()), (0, True))
        radio = fake_qt.RadioButton("High", self.panel, name="qtHigh", checked=True)    # a click does not turn it off
        result = self.run_value(object_name="qtHigh", value=False)
        self.assertFalse(result["success"])
        self.assertIn("the widget shows True", result["error"])
        self.assertEqual(radio.clicks, 1)

    def test_the_value_it_already_has_sends_nothing(self) -> None:
        seen = []
        self.preview.editingFinished.connect(lambda: seen.append(1))
        result = self.run_value(object_name="qtSpinBox", ancestor="qtPreviewComboSpinBox", value=1)
        self.assertTrue(result["success"], result)
        self.assertIn("already had that value", result["note"])
        self.assertEqual((self.preview.set_calls, seen, result["changed"]), ([], [], False))
        self.assertNotIn("signals_sent", result)

    def test_screenshot_false_returns_no_pictures(self) -> None:
        result = self.run_value(object_name="qtOpacitySlider", value=20, screenshot=False)
        self.assertTrue(result["success"])
        self.assertNotIn("png_base64", result)
        self.assertEqual(self.main.grabbed, 0)


class RefusalTest(ValueTestCase):
    def test_disabled_and_read_only_widgets(self) -> None:
        self.slider._enabled = False
        self.assert_refused(self.value(object_name="qtOpacitySlider", value=20), "disabled")
        self.render.isReadOnly = lambda: True
        self.assert_refused(self.value(object_name="qtSpinBox", ancestor="qtRenderComboSpinBox", value=1), "read-only")

    def test_money_words_in_the_object_name_tool_tip_label_or_placeholder(self) -> None:
        buy = fake_qt.SpinBox(self.panel, name="qtBuyCountSpinBox", value=1)
        self.assert_refused(self.value(object_name="qtBuyCountSpinBox", value=2), "refused", "mentions 'buy'")
        self.slider._tooltip = "<b>Pur</b>chase amount"
        self.assert_refused(self.value(object_name="qtOpacitySlider", value=20), "mentions 'purchase'")
        row = fake_qt.Widget(name="qtRow", parent=self.panel)
        fake_qt.Label("Price", row)
        priced = fake_qt.SpinBox(row, name="qtAmount", value=1)
        self.assert_refused(self.value(object_name="qtAmount", value=2), "mentions 'price'")
        coupon = fake_qt.LineEdit(self.panel, placeholder="Enter your coupon", name="qtCodeEdit")
        self.assert_refused(self.value(object_name="qtCodeEdit", value="ABC"), "mentions 'coupon'")
        agree = fake_qt.CheckBox("I agree to the terms", self.panel, name="qtAgree")
        agree.auto_toggle = True
        self.assert_refused(self.value(object_name="qtAgree", value=True), "refused")
        self.assertEqual((buy.set_calls, priced.set_calls, coupon.set_calls, agree.clicks), ([], [], [], 0))

    def test_a_buddy_label_counts_and_many_labels_in_one_parent_do_not(self) -> None:
        label = fake_qt.Label("Credits to spend", self.main)
        label.buddy = lambda: self.double
        self.assert_refused(self.value(object_name="qtWeight", value=0.5), "mentions 'credit'")
        label.buddy = lambda: None
        for text in ("Opacity", "Weight", "Material", "Price list"):      # a whole form: not this widget's labels
            fake_qt.Label(text, self.panel)
        self.assertTrue(self.run_value(object_name="qtWeight", value=0.5)["success"])

    def test_delete_login_and_sort_order_widgets_are_set(self) -> None:
        for i, (name, tip) in enumerate((("qtDeleteCount", ""), ("qtLoginRetries", ""), ("qtSort", "Sort order"),
                                         ("qtLayer", "Layer order"), ("qtPhysics", "Activate Physics strength"))):
            with self.subTest(name=name):
                spin = fake_qt.SpinBox(self.panel, name=name, value=0, lo=0, hi=9)
                spin._tooltip = tip
                self.assertTrue(self.run_value(object_name=name, value=i + 1)["success"])
                self.assertEqual(spin.value(), i + 1)

    def test_the_allowlist_lets_exactly_the_wrinkle_check_box_ignore_activate(self) -> None:
        self.wrinkle._tooltip = "Activate"                   # alone, this word refuses (see the twin below)
        self.assertTrue(self.run_value(object_name="qtActiveWrinkleCheckBox", value=True)["success"])
        self.assertEqual(self.wrinkle.clicks, 1)
        twin = fake_qt.CheckBox("Activate Expression Wrinkles", self.panel, name="qtActiveWrinkleCheckBox2")
        twin._tooltip = "Activate"
        twin.auto_toggle = True
        self.wrinkle.clicks = 0
        self.assert_refused(self.value(object_name="qtActiveWrinkleCheckBox2", value=True), "mentions 'activat'")
        self.wrinkle._text = "Activate Expression Wrinkles Pro"       # the same objectName, another text
        self.assert_refused(self.value(object_name="qtActiveWrinkleCheckBox", value=True), "mentions 'activat'")
        self.wrinkle._text = "Activate Expression Wrinkles"
        self.wrinkle._tooltip = "Activate (needs a licence)"          # every other word still refuses
        self.assert_refused(self.value(object_name="qtActiveWrinkleCheckBox", value=True), "refused", "licen")
        self.assertEqual(twin.clicks, 0)

    def test_the_allowlist_does_not_open_a_money_window(self) -> None:
        self.dialog("Activation", "Activate this product online?", ["OK", "Cancel"])
        self.assert_refused(self.value(object_name="qtActiveWrinkleCheckBox", value=True), "a person must decide")

    def test_nothing_is_set_while_a_window_needs_a_person(self) -> None:
        self.dialog("Store", "Purchase this pack?", ["Buy", "Cancel"])
        self.assert_refused(self.value(object_name="qtOpacitySlider", value=20), "a person must decide")

    def test_a_login_or_update_window_does_not_block(self) -> None:
        self.dialog("Update", "Update available", ["OK"])
        self.assertTrue(self.run_value(object_name="qtOpacitySlider", value=20)["success"])

    def test_a_modal_window_blocks_widgets_outside_it_but_not_inside(self) -> None:
        dlg = self.dialog("Export Settings", "Choose", ["OK", "Cancel"])
        dlg._modal = True
        inside = fake_qt.SpinBox(dlg, name="qtExportSize", value=1, lo=0, hi=9)
        self.assert_refused(self.value(object_name="qtOpacitySlider", value=20), "modal window 'Export Settings' is open")
        result = self.run_value(window="Export Settings", object_name="qtExportSize", value=5)
        self.assertTrue(result["success"], result)
        self.assertEqual(inside.value(), 5)
        self.assertEqual([b.clicks for b in dlg.findChildren(fake_qt.PushButton)], [0, 0])


class JobTest(ValueTestCase):
    def test_the_change_runs_on_a_qt_timer_and_the_picture_comes_after_wait_ms(self) -> None:
        started = self.value(object_name="qtOpacitySlider", value=30, wait_ms=2500)
        self.assertTrue(started["success"], started)
        self.assertTrue(started["job_id"].startswith("value-"))
        fake_qt.drain(1)                                     # the job's first step: schedules the change
        self.assertEqual(fake_qt.Timer.pending_ms(), [cc5_uivalue.SET_DELAY_MS, cc5_uivalue.SET_DELAY_MS + 2500])
        self.assertEqual(self.slider.calls, [])
        result = self.finish(started)
        self.assertEqual((self.slider.value(), result["waited_ms"]), (30, 2500))

    def test_the_widget_is_checked_again_when_the_job_starts(self) -> None:
        started = self.value(object_name="qtOpacitySlider", value=30)
        self.slider._enabled = False                         # greyed out before the job's first step
        result = self.finish(started)
        self.assertFalse(result["success"])
        self.assertIn("disabled", result["error"])
        self.assertEqual(self.slider.calls, [])

    def test_a_change_that_raises_or_does_not_take_is_reported(self) -> None:
        def boom(_value: int) -> None:
            raise RuntimeError("Internal C++ object already deleted")

        self.render.on_change = boom
        result = self.run_value(object_name="qtSpinBox", ancestor="qtRenderComboSpinBox", value=1)
        self.assertFalse(result["success"])
        self.assertIn("RuntimeError", result["error"])
        self.preview.on_change = lambda _value: setattr(self.preview, "_value", 1)      # CC5 puts it back
        result = self.run_value(object_name="qtSpinBox", ancestor="qtPreviewComboSpinBox", value=2)
        self.assertFalse(result["success"])
        self.assertIn("asked for 2 but the widget shows 1", result["error"])

    def test_a_window_the_change_opened_is_reported_and_not_answered(self) -> None:
        opened = []
        self.wrinkle.on_click = lambda: opened.append(self.dialog("Note", "Loading wrinkle maps.", ["OK"]))
        result = self.run_value(object_name="qtActiveWrinkleCheckBox", value=True)
        self.assertTrue(result["success"], result)
        self.assertEqual([d["title"] for d in result["dialogs"]], ["Note"])
        self.assertEqual([b.clicks for b in opened[0].findChildren(fake_qt.PushButton)], [0])

    def test_one_ui_job_at_a_time(self) -> None:
        cc5_ui.start_job("other", lambda p: {"success": True}, {})
        res = self.value(object_name="qtOpacitySlider", value=30)
        self.assertFalse(res["success"])
        self.assertIn("another UI job", res["error"])


class ArgumentsTest(ValueTestCase):
    def test_bad_requests_are_refused_before_anything_runs(self) -> None:
        ok = {"window": "MainWindow", "object_name": "qtOpacitySlider"}
        bad = (
            {},
            {"object_name": "qtOpacitySlider", "value": 1},
            {"window": "MainWindow", "value": 1},
            {**ok},                                          # no value and not read_only
            {**ok, "value": None},
            {**ok, "value": [1]},
            {**ok, "value": {"index": 1}},
            {**ok, "value": float("nan")},
            {**ok, "value": float("inf")},
            {**ok, "value": "x" * 2000},
            {**ok, "window": "", "value": 1},
            {**ok, "object_name": 3, "value": 1},
            {**ok, "ancestor": "", "value": 1},
            {**ok, "ancestor": "x" * 300, "value": 1},
            {**ok, "value": 1, "read_only": "no"},
            {**ok, "value": 1, "screenshot": "yes"},
            {**ok, "value": 1, "text": "Opacity"},
            {**ok, "value": 1, "menu_item": "Save"},
            {**ok, "value": 1, "index": 2},
        )
        for body in bad:
            with self.subTest(body=body):
                self.assertFalse(cc5_uivalue.ui_value(body)["success"])
        self.assertEqual(fake_qt.Timer.singles, [])
        self.assert_untouched()

    def test_wait_ms_default_and_limits(self) -> None:
        def wait(value: object = None) -> int:
            body = {"window": "w", "object_name": "n", "value": 1}
            if value is not None:
                body["wait_ms"] = value
            return cc5_uivalue.read_args(body)[0]["wait_ms"]

        self.assertEqual(wait(), cc5_uivalue.DEFAULT_WAIT_MS)
        self.assertEqual(wait(999_999), cc5_uivalue.MAX_WAIT_MS)
        self.assertEqual(wait(1), cc5_uivalue.MIN_WAIT_MS)
        self.assertEqual(wait("nope"), cc5_uivalue.DEFAULT_WAIT_MS)

    def test_route_and_shared_limits(self) -> None:
        self.assertEqual(cc5_uivalue.ROUTES, {"/ui/value": ("ui_value", cc5_uivalue.ui_value)})
        self.assertEqual(cc5_uivalue.MAX_WAIT_MS, cc5_uiclick.MAX_WAIT_MS)


if __name__ == "__main__":
    unittest.main()
