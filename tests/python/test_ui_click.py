"""
cc5_uiclick: press ONE named button of a CC5 window (/ui/click), with a fake Qt.

What is checked: the matching (window by title or objectName, button by objectName and/or text,
menu entries), every refusal (no match, ambiguous, hidden, disabled, the deny words, a window that
needs a person, a modal window), and the job (click on a Qt timer, picture after wait_ms, a click that
opens a modal window, a click that raises).

    python -m unittest discover -s tests/python -v      (or: npm run test:py)
"""

from __future__ import annotations

import json
import unittest

from ui_support import UiTestCase, cc5_ui, fake_qt

import cc5_uiclick  # noqa: E402


class ClickTestCase(UiTestCase):
    """A floating tool window like Body Wrap, with two buttons."""

    def setUp(self) -> None:
        super().setUp()
        self.win = self.tool_window("Body Wrap", name="BodyWrapWindow")
        self.save = fake_qt.PushButton("Save Skeleton", self.win, name="qtSaveSkeletonButton")
        self.paste = fake_qt.PushButton("Paste", self.win, name="qtPasteButton")

    def tool_window(self, title: str, name: str = "") -> fake_qt.Widget:
        w = fake_qt.Widget(name=name, title=title)
        w._is_window = True
        self.q.app.tops.append(w)
        return w

    def click(self, **body):
        body.setdefault("window", "Body Wrap")
        return cc5_uiclick.ui_click(body)

    def run_click(self, **body):
        return self.finish(self.click(**body))

    def assert_refused(self, res: dict, *needles: str) -> None:
        self.assertFalse(res["success"], res)
        for needle in needles:
            self.assertIn(needle, res["error"])
        self.assertEqual(fake_qt.Timer.singles, [], "a refused request must not start a job")


class MatchingTest(ClickTestCase):
    def test_presses_the_button_by_text_and_returns_picture_and_dialogs(self) -> None:
        result = self.run_click(text="Save Skeleton")
        self.assertTrue(result["success"], result)
        self.assertEqual((self.save.clicks, self.paste.clicks), (1, 0))
        self.assertTrue(result["click_returned"])
        self.assertEqual(result["window"], "Body Wrap")
        self.assertEqual(result["pressed"]["object_name"], "qtSaveSkeletonButton")
        self.assertTrue(result["window_open"])
        self.assertTrue(result["png_base64"])
        self.assertEqual(self.win.grabbed, 1)
        self.assertEqual(result["dialogs"], [])
        self.assertNotIn("checked_before", result)

    def test_by_object_name_and_by_loose_case_and_spacing(self) -> None:
        self.run_click(object_name="qtPasteButton")
        self.run_click(text="  save   SKELETON ")
        self.run_click(text="&Paste")
        self.assertEqual((self.save.clicks, self.paste.clicks), (1, 2))

    def test_shortcut_marker_on_the_button_is_ignored(self) -> None:
        detect = fake_qt.PushButton("&Detect Joints", self.win, name="qtDetect")
        self.run_click(text="Detect Joints")
        self.assertEqual(detect.clicks, 1)

    def test_window_by_title_any_case_or_by_object_name(self) -> None:
        self.run_click(window="BODY WRAP", text="Paste")
        self.run_click(window="BodyWrapWindow", text="Paste")
        self.assertEqual(self.paste.clicks, 2)

    def test_unknown_window_lists_the_open_ones(self) -> None:
        self.assert_refused(self.click(window="Headshot", text="Paste"), "no open CC5 window", "'Body Wrap'")

    def test_two_windows_with_one_title_are_ambiguous_until_the_object_name_picks_one(self) -> None:
        self.tool_window("Body Wrap")
        self.assert_refused(self.click(text="Paste"), "2 open windows are called")
        self.run_click(window="BodyWrapWindow", text="Paste")
        self.assertEqual(self.paste.clicks, 1)

    def test_no_such_button_lists_the_visible_ones_only(self) -> None:
        fake_qt.PushButton("Secret", self.win, visible=False)
        res = self.click(text="Load Skeleton")
        self.assert_refused(res, "no button with text 'Load Skeleton'", "'Save Skeleton' [qtSaveSkeletonButton]")
        self.assertNotIn("Secret", res["error"])

    def test_two_visible_matches_are_ambiguous_until_object_name_picks_one(self) -> None:
        other = fake_qt.PushButton("Paste", self.win, name="qtPasteHair")
        self.assert_refused(self.click(text="Paste"), "2 visible buttons match", "qtPasteHair")
        self.run_click(text="Paste", object_name="qtPasteHair")
        self.assertEqual((other.clicks, self.paste.clicks), (1, 0))

    def test_hidden_duplicates_do_not_count_and_are_never_pressed(self) -> None:
        ghost = fake_qt.PushButton("Paste", self.win, name="qtPasteGhost", visible=False)
        result = self.run_click(text="Paste")
        self.assertEqual((self.paste.clicks, ghost.clicks), (1, 0))
        self.assertEqual(result["hidden_skipped"], 1)
        only_hidden = fake_qt.PushButton("Bake", self.win, visible=False)
        self.assert_refused(self.click(text="Bake"), "is hidden")
        self.assertEqual(only_hidden.clicks, 0)

    def test_buttons_of_a_child_dialog_belong_to_that_dialog(self) -> None:
        child = fake_qt.Dialog(title="Confirm", parent=self.win)
        ok = fake_qt.PushButton("OK", child)
        self.assert_refused(self.click(text="OK"), "no button with text 'OK'")
        self.assertEqual(ok.clicks, 0)

    def test_a_dock_panel_inside_the_main_window(self) -> None:
        main = fake_qt.MainWindow(title="Character Creator 5 - test.ccProject")
        self.q.app.tops.append(main)
        dock = fake_qt.DockWidget(name="qtModifyDock", title="Modify", parent=main)
        refresh = fake_qt.PushButton("Refresh", dock, name="qtRefresh")
        result = self.run_click(window="Modify", text="Refresh")
        self.assertEqual(refresh.clicks, 1)
        self.assertEqual(dock.grabbed, 1)                    # the picture is of the panel that was named
        self.assertEqual(result["window"], "Modify")


class RefusalTest(ClickTestCase):
    # group 1 of the policy of 2026-11-19: money (MONEY) and agreements (AGREEMENT)
    REFUSED = (
        "Generate AI Points", "Align Points (AI)", "Get AI Points", "Wrap Points", "ポイントを使う", "Buy Now", "ＢＵＹ", "購入する", "Purchase",
        "pUrChAsE", "Pur chase", "Place Order", "Checkout", "Add to Cart", "Credits", "クレジット", "Subscribe",
        "Subscription", "Pay", "Payment", "支払い", "Show Prices", "Upgrade", "Start Trial", "Activate", "Deactivate",
        "Activation", "License", "Licence info", "ライセンス",
        "Terms of Use", "I Agree", "Accept Agreement", "EULA", "規約に同意",
    )
    # refused until 2026-11-19, pressed since (the owner's money-only rule)
    ALLOWED = ("Delete", "削除", "Remove Layer", "Log In", "Login", "Sign in", "ログイン", "Update", "更新",
               "Register", "Account", "Unlock", "Overwrite", "Install", "Cartoon", "Border", "Reorder")

    def test_every_deny_word_in_the_text_is_refused(self) -> None:
        for i, label in enumerate(self.REFUSED):
            with self.subTest(label=label):
                button = fake_qt.PushButton(label, self.win, name=f"qtB{i}")
                self.assert_refused(self.click(object_name=f"qtB{i}"), "refused")
                self.assertEqual(button.clicks, 0)

    def test_delete_login_update_and_the_like_are_pressed_now(self) -> None:
        for i, label in enumerate(self.ALLOWED):
            with self.subTest(label=label):
                button = fake_qt.PushButton(label, self.win, name=f"qtA{i}")
                result = self.run_click(object_name=f"qtA{i}")
                self.assertTrue(result["success"], result)
                self.assertEqual(button.clicks, 1)
        trash = fake_qt.ToolButton("", self.win, name="qtDeleteToolButton")
        trash._tooltip = "Remove the selected layer"
        self.run_click(object_name="qtDeleteToolButton")
        self.assertEqual(trash.clicks, 1)

    def test_deny_word_in_the_object_name_or_the_tool_tip(self) -> None:
        trash = fake_qt.ToolButton("", self.win, name="qtBuyToolButton")
        self.assert_refused(self.click(object_name="qtBuyToolButton"), "mentions 'buy'")
        tip = fake_qt.PushButton("OK", self.win, name="qtOk")
        tip._tooltip = "<html><b>Pur</b>chase this item</html>"
        self.assert_refused(self.click(object_name="qtOk"), "mentions 'purchase'")
        points = fake_qt.PushButton("Go", self.win, name="qtGo")
        points._tooltip = "Replace the hand-fixed points"
        self.assert_refused(self.click(object_name="qtGo"), "mentions 'point'")
        self.assertEqual((trash.clicks, tip.clicks, points.clicks), (0, 0, 0))

    def test_owner_exception_presses_exactly_the_two_wrap_point_buttons(self) -> None:
        gen = fake_qt.PushButton("GENERATE WRAP POINTS", self.win, name="qtGenerateWrapPointsButton")
        gen._tooltip = "Generate the wrap points"
        align = fake_qt.PushButton("&Align Points", self.win, name="qtAlignPointsButton")
        self.run_click(text="Generate Wrap Points")
        self.run_click(object_name="qtAlignPointsButton")
        self.assertEqual((gen.clicks, align.clicks), (1, 1))

    def test_exception_still_refuses_any_other_deny_word_and_similar_names(self) -> None:
        credit = fake_qt.PushButton("Align Points", self.win, name="qtAlignCredit")
        credit._tooltip = "Costs one credit"
        buy = fake_qt.PushButton("Generate Wrap Points", self.win, name="qtBuyWrapPoints")
        buy._tooltip = ""
        self.assert_refused(self.click(object_name="qtAlignCredit"), "mentions 'credit'")
        self.assert_refused(self.click(object_name="qtBuyWrapPoints"), "mentions 'buy'")
        self.assertEqual((credit.clicks, buy.clicks), (0, 0))

    def test_exception_is_only_inside_the_body_wrap_window_and_not_for_menu_entries(self) -> None:
        other = self.tool_window("Headshot 3", name="HeadshotWindow")
        elsewhere = fake_qt.PushButton("Align Points", other, name="qtAlignElsewhere")
        self.assert_refused(self.click(window="Headshot 3", text="Align Points"), "mentions 'point'")
        self.assertEqual(elsewhere.clicks, 0)
        self.assertIsNone(cc5_uiclick.deny_reason("Generate Wrap Points", skip_words=frozenset({"point"})))
        self.assertEqual(cc5_uiclick.deny_reason("Generate Wrap Points"), "point")

    def test_feature_switches_with_activate_are_pressed_and_licence_ones_are_not(self) -> None:
        for i, label in enumerate(("Activate Physics", "Activate Expression Wrinkles", "Deactivate Mirror",
                                   "Activate Editor", "Reactivate Layer")):
            with self.subTest(label=label):
                button = fake_qt.PushButton(label, self.win, name=f"qtOn{i}")
                self.assertTrue(self.run_click(object_name=f"qtOn{i}")["success"])
                self.assertEqual(button.clicks, 1)
        for i, (label, name, tip) in enumerate((("Activate", "", ""), ("Activation", "", ""), ("Activate Now", "", ""),
                                                ("Activate Product", "", ""), ("Online Activation", "", ""),
                                                ("Activate License", "", ""), ("Enter Activation Key", "", ""),
                                                ("Activate Physics", "qtActivateSerialButton", ""),
                                                ("Activate Physics", "", "Activate your account first"),
                                                ("", "qtActivateToolButton", ""), ("Acti vate Physics", "", ""))):
            with self.subTest(label=label, name=name, tip=tip):
                button = fake_qt.PushButton(label, self.win, name=name or f"qtOff{i}")
                button._tooltip = tip
                self.assert_refused(self.click(object_name=name or f"qtOff{i}"), "refused", "mentions")
                self.assertEqual(button.clicks, 0)

    def test_sort_order_buttons_are_pressed_and_order_now_is_not(self) -> None:
        for i, label in enumerate(("Sort Order", "Draw Order", "Render Order", "Layer Order", "Order by Name",
                                   "Reorder", "In order to bake, press here")):
            with self.subTest(label=label):
                button = fake_qt.PushButton(label, self.win, name=f"qtSeq{i}")
                self.assertTrue(self.run_click(object_name=f"qtSeq{i}")["success"])
                self.assertEqual(button.clicks, 1)
        for i, (label, tip) in enumerate((("Order Now", ""), ("Place Order", ""), ("Your Order", ""),
                                          ("Order Summary", ""), ("Order ID", ""), ("Orders", ""), ("Sort Orders", ""),
                                          ("Sort", "Order"), ("Sort Order", "Place your order"))):
            with self.subTest(label=label, tip=tip):
                button = fake_qt.PushButton(label, self.win, name=f"qtNo{i}")
                button._tooltip = tip
                self.assert_refused(self.click(object_name=f"qtNo{i}"), "mentions 'order'")
                self.assertEqual(button.clicks, 0)

    def test_ordinary_buttons_are_not_caught_by_the_short_words(self) -> None:
        for label in ("Display", "Replay", "Repaint", "Detect Joints", "Paste", "Save Skeleton", "Load Skeleton",
                      "Bake Textures", "Create CC Actor", "Refine Mesh", "Generate Skeleton", "OK", "Cancel",
                      "Cartoon Shader", "Border Width", "Reorder", "Delete", "Remove", "Log In", "Update"):
            self.assertIsNone(cc5_uiclick.deny_reason(label, "qtButton", ""), label)

    def test_deny_reason_names_the_word(self) -> None:
        self.assertEqual(cc5_uiclick.deny_reason("Generate Wrap Points"), "point")
        self.assertEqual(cc5_uiclick.deny_reason("", "qtBuyButton"), "buy")
        self.assertEqual(cc5_uiclick.deny_reason("Check out", "qtCheckoutButton"), "checkout")
        self.assertEqual(cc5_uiclick.deny_reason("Terms"), "terms")
        self.assertEqual(cc5_uiclick.deny_reason("Save", "", "<b>Pur</b>chase all"), "purchase")
        self.assertIsNone(cc5_uiclick.deny_reason("Log In"))
        self.assertIsNone(cc5_uiclick.deny_reason("Save", "", "<b>Del</b>ete all"))

    def test_the_word_list_is_the_agreed_one(self) -> None:
        self.assertEqual(set(cc5_uiclick.DENY_WORDS), {
            "point", "ポイント", "buy", "購入", "purchase", "license", "licence",
            "ライセンス", "activate", "upgrade", "credit", "クレジット", "subscribe", "pay", "支払"})
        self.assertEqual(set(cc5_ui.MONEY_WORDS), {"pay", "paid", "price", "pricing", "order", "cart", "credit"})
        self.assertEqual(set(cc5_ui.AGREEMENT_STEMS), {"agree", "terms", "eula"})
        for gone in ("delete", "remove", "log in", "login", "sign in", "updat", "password", "account", "register"):
            self.assertNotIn(gone, cc5_uiclick.DENY_WORDS + cc5_ui.MONEY_STEMS + cc5_ui.MONEY_WORDS + cc5_ui.AGREEMENT_STEMS)

    def test_disabled_button_is_refused(self) -> None:
        self.save._enabled = False
        self.assert_refused(self.click(text="Save Skeleton"), "disabled")
        self.assertEqual(self.save.clicks, 0)

    def test_nothing_is_pressed_while_a_window_needs_a_person(self) -> None:
        self.dialog("License", "Your license has expired", ["OK"])
        self.assert_refused(self.click(text="Paste"), "a person must decide")
        self.assertEqual(self.paste.clicks, 0)

    def test_every_money_or_agreement_window_blocks_all_presses(self) -> None:
        windows = (("Store", "Purchase this pack?"), ("Store", "Buy now"), ("Order", "Confirm your order"),
                   ("Checkout", "Review"), ("Cart", "2 items in your cart"), ("Content", "This costs 5 credits"),
                   ("Plan", "Your subscription ends soon"), ("Store", "Payment method"), ("Store", "Price: 5 USD"),
                   ("Info", "A paid upgrade is available"), ("Info", "Start your free trial"),
                   ("Activation", "Enter the key"), ("Info", "Activate this product"), ("License", "Expired"),
                   ("Store", "Use DA Points?"), ("確認", "購入しますか"), ("Terms of Use", "Read"),
                   ("Info", "I agree to the agreement"), ("EULA", "Read"), ("確認", "利用規約に同意"))
        for title, text in windows:
            with self.subTest(title=title, text=text):
                dlg = self.dialog(title, text, ["OK", "Cancel"])
                self.assert_refused(self.click(text="Paste"), "a person must decide", "money or an agreement")
                self.assert_refused(self.click(window=title, text="Cancel"), "a person must decide")
                self.assertEqual([b.clicks for b in dlg.findChildren(fake_qt.PushButton)], [0, 0])
                self.q.app.tops.remove(dlg)
        self.assertEqual(self.paste.clicks, 0)

    def test_login_update_and_delete_windows_do_not_block_and_can_be_answered(self) -> None:
        windows = (("Login", "Log in with your account", ["Sign in", "Cancel"]),
                   ("Update", "A new update is available. Update now?", ["Update", "Later"]),
                   ("Delete", "Delete all layers?", ["Delete", "No"]),
                   ("Confirm", "Overwrite the existing file?", ["Yes", "No"]))
        for n, (title, text, buttons) in enumerate(windows, 1):
            with self.subTest(title=title):
                dlg = self.dialog(title, text, buttons)
                fake_qt.LineEdit(dlg, echo=fake_qt.LineEdit.Password)
                self.run_click(text="Paste")
                self.assertEqual(self.paste.clicks, n)
                self.run_click(window=title, text=buttons[0])
                self.assertEqual([b.clicks for b in dlg.findChildren(fake_qt.PushButton)], [1, 0])
                self.q.app.tops.remove(dlg)

    def test_a_modal_window_blocks_buttons_outside_it_but_not_inside(self) -> None:
        dlg = self.dialog("Save Skeleton", "Choose a file name", ["Save", "Cancel"])
        dlg._modal = True
        self.assert_refused(self.click(text="Paste"), "modal window 'Save Skeleton' is open")
        self.run_click(window="Save Skeleton", text="Cancel")
        cancel = [b for b in dlg.findChildren(fake_qt.PushButton) if b.text() == "Cancel"][0]
        self.assertEqual((self.paste.clicks, cancel.clicks), (0, 1))


class AllowlistTest(ClickTestCase):
    """cc5_uiclick.ALLOWLIST: exact controls that may ignore ONE named word (the Body Wrap entries are tested
    above and in MenuTest; here: the table itself and the Expression Wrinkles check box)."""

    def setUp(self) -> None:
        super().setUp()
        self.main = fake_qt.MainWindow(name="MainWindow", title="Character Creator 5 - test.ccProject")
        self.q.app.tops.append(self.main)
        self.dock = fake_qt.DockWidget(name="qtModifyDock", title="Modify", parent=self.main)
        self.box = fake_qt.CheckBox("Activate Expression Wrinkles", self.dock, name="qtActiveWrinkleCheckBox")
        self.box._tooltip = "Activate"                       # alone, this word refuses any other control

    def test_the_table_is_the_agreed_one(self) -> None:
        rows = {(e.window_title, e.window_object_name, e.kind, e.object_name, e.text, tuple(sorted(e.ignore)))
                for e in cc5_uiclick.ALLOWLIST}
        points = ("point", "ポイント")
        self.assertEqual(rows, {
            ("body wrap", None, "control", None, "generate wrap points", points),
            ("body wrap", None, "control", None, "align points", points),
            ("body wrap", None, "menu_entry", None, "save wrap points", points),
            ("body wrap", None, "menu_entry", None, "load wrap points", points),
            (None, "MainWindow", "control", "qtActiveWrinkleCheckBox", "activate expression wrinkles", ("activat",)),
        })
        for entry in cc5_uiclick.ALLOWLIST:
            self.assertTrue(entry.window_title or entry.window_object_name)
            self.assertTrue(entry.text and entry.why)
            self.assertEqual(entry.text, cc5_uiclick.label_key(entry.text))
            if entry.window_title != "body wrap":            # only the old Body Wrap rows may leave the objectName open
                self.assertTrue(entry.object_name)
        self.assertEqual(cc5_uiclick.POINT_EXCEPTION_BUTTONS, {"generate wrap points", "align points"})
        self.assertEqual(cc5_uiclick.POINT_EXCEPTION_MENU_ENTRIES, {"save wrap points", "load wrap points"})

    def test_the_wrinkle_check_box_is_pressed_from_the_main_window_or_its_dock_panel(self) -> None:
        self.assertTrue(self.run_click(window="MainWindow", object_name="qtActiveWrinkleCheckBox")["success"])
        self.assertTrue(self.run_click(window="Modify", text="activate expression wrinkles")["success"])
        self.assertEqual(self.box.clicks, 2)
        self.assertEqual(cc5_uiclick.allowlist_ignores(self.dock, "qtActiveWrinkleCheckBox", "Activate Expression Wrinkles"),
                         {"activat"})

    def test_a_similar_control_stays_refused(self) -> None:
        cases = (("qtActiveWrinkleCheckBox2", "Activate Expression Wrinkles"),        # another objectName
                 ("qtActiveWrinkleCheckBox", "Activate Expression Wrinkles Pro"),     # another text
                 ("qtactivewrinklecheckbox", "Activate Expression Wrinkles"))         # the objectName is case-sensitive
        self.box._visible = False
        for name, text in cases:
            with self.subTest(name=name, text=text):
                twin = fake_qt.CheckBox(text, self.dock, name=name)
                twin._tooltip = "Activate"
                self.assert_refused(self.click(window="MainWindow", object_name=name), "mentions 'activat'")
                self.assertEqual(twin.clicks, 0)
                twin._visible = False
        self.assertEqual(cc5_uiclick.allowlist_ignores(self.dock, "qtActiveWrinkleCheckBox", "Activate"), frozenset())
        self.assertEqual(cc5_uiclick.allowlist_ignores(None, "qtActiveWrinkleCheckBox", "Activate Expression Wrinkles"),
                         frozenset())

    def test_the_entry_is_only_for_the_main_window(self) -> None:
        same = fake_qt.CheckBox("Activate Expression Wrinkles", self.win, name="qtActiveWrinkleCheckBox")
        same._tooltip = "Activate"
        self.assert_refused(self.click(window="Body Wrap", object_name="qtActiveWrinkleCheckBox"), "mentions 'activat'")
        self.assertEqual(same.clicks, 0)

    def test_every_other_word_still_refuses_the_allowlisted_control(self) -> None:
        for tip, word in (("Activate your licence", "licen"), ("Costs 5 credits", "credit"), ("Buy the wrinkle pack", "buy"),
                          ("Uses AI points", "point")):
            with self.subTest(tip=tip):
                self.box._tooltip = tip
                self.assert_refused(self.click(window="MainWindow", object_name="qtActiveWrinkleCheckBox"), "refused", word)
        self.assertEqual(self.box.clicks, 0)

    def test_an_entry_never_presses_while_a_money_or_agreement_window_is_open(self) -> None:
        for title, text in (("Activation", "Activate this product online?"), ("Terms of Use", "Read")):
            with self.subTest(title=title):
                dlg = self.dialog(title, text, ["OK", "Cancel"])
                self.assert_refused(self.click(window="MainWindow", object_name="qtActiveWrinkleCheckBox"),
                                    "a person must decide")
                self.q.app.tops.remove(dlg)
        gen = fake_qt.PushButton("Generate Wrap Points", self.win, name="qtGenerateWrapPointsButton")
        self.dialog("Store", "Use DA Points?", ["OK"])
        self.assert_refused(self.click(text="Generate Wrap Points"), "a person must decide")
        self.assertEqual((self.box.clicks, gen.clicks), (0, 0))

    def test_structural_refusals_stay_for_an_allowlisted_control(self) -> None:
        self.box._enabled = False
        self.assert_refused(self.click(window="MainWindow", object_name="qtActiveWrinkleCheckBox"), "disabled")
        self.box._enabled, self.box._visible = True, False
        self.assert_refused(self.click(window="MainWindow", object_name="qtActiveWrinkleCheckBox"), "is hidden")


class UnsavedBoxTest(ClickTestCase):
    """CC5's start-up 'Unsaved project data found' box: "update" is no refused word any more (2026-11-19),
    so both buttons can be pressed; the box is found although the main window has the same title."""

    TEXT = "Unsaved project data found. Would you like to update your project with the unsaved changes?"

    def box(self, text: str | None = None, buttons: list[str] | None = None):
        dlg = self.dialog("Character Creator 5", text or self.TEXT, buttons or ["OK", "Cancel"])
        dlg._modal = True
        return dlg

    def button(self, dlg, label: str):
        return [b for b in dlg.findChildren(fake_qt.PushButton) if b.text() == label][0]

    def test_cancel_of_the_exact_box_is_pressed(self) -> None:
        dlg = self.box()
        self.run_click(window="Character Creator 5", text="Cancel")
        self.assertEqual((self.button(dlg, "Cancel").clicks, self.button(dlg, "OK").clicks), (1, 0))

    def test_ok_of_the_box_can_be_pressed_too_now(self) -> None:
        dlg = self.box()
        self.run_click(window="Character Creator 5", text="OK")
        self.assertEqual((self.button(dlg, "Cancel").clicks, self.button(dlg, "OK").clicks), (0, 1))

    def test_the_box_is_taken_although_the_main_window_has_the_same_title(self) -> None:
        main = fake_qt.MainWindow(title="Character Creator 5")
        self.q.app.tops.append(main)
        fake_qt.PushButton("Cancel", main, name="qtMainCancel")
        dlg = self.box()
        self.run_click(window="Character Creator 5", text="Cancel")
        self.assertEqual(self.button(dlg, "Cancel").clicks, 1)

    def test_buttons_outside_the_modal_box_stay_blocked_by_the_modal_rule(self) -> None:
        self.box()
        self.assert_refused(self.click(text="Paste"), "modal window 'Character Creator 5' is open")
        self.assertEqual(self.paste.clicks, 0)

    def test_a_box_that_mentions_money_is_still_refused(self) -> None:
        for kwargs in ({"text": "A paid upgrade is available. Would you like to purchase it now?"},
                       {"buttons": ["OK", "Cancel", "Buy"]}):
            with self.subTest(kwargs):
                dlg = self.box(**kwargs)
                self.assert_refused(self.click(window="Character Creator 5", text="Cancel"), "a person must decide")
                self.assertEqual(self.button(dlg, "Cancel").clicks, 0)
                self.q.app.tops.remove(dlg)



class MenuTest(ClickTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.load = fake_qt.Action("Load Skeleton")
        self.store = fake_qt.Action("Save Skeleton")
        self.disk = fake_qt.ToolButton("", self.win, name="qtSkeletonFileButton")
        self.disk._tooltip = "Skeleton file"
        self.entries = [self.load, fake_qt.Action("", separator=True), self.store]
        self.disk._menu = fake_qt.ActionMenu(self.entries)

    def test_menu_item_triggers_that_entry_not_the_button(self) -> None:
        result = self.run_click(object_name="qtSkeletonFileButton", menu_item="save skeleton")
        self.assertTrue(result["success"], result)
        self.assertEqual((self.store.triggered, self.load.triggered, self.disk.clicks), (1, 0, 0))
        self.assertEqual(result["pressed"]["menu_item"], "save skeleton")
        self.assertEqual(result["pressed"]["tooltip"], "Skeleton file")

    def test_a_menu_button_without_menu_item_is_refused_and_lists_the_entries(self) -> None:
        self.assert_refused(self.click(object_name="qtSkeletonFileButton"), "drop-down menu",
                            "'Load Skeleton', 'Save Skeleton'", "menu_item")
        self.assertEqual(self.disk.clicks, 0)

    def test_menu_entry_refusals(self) -> None:
        self.entries += [fake_qt.Action("Hidden", visible=False), fake_qt.Action("Buy Skeleton"),
                         fake_qt.Action("More", submenu=fake_qt.ActionMenu([]))]
        cases = (("Export", "is not there"), ("Hidden", "is hidden"), ("More", "sub-menu"),
                 ("Buy Skeleton", "mentions 'buy'"))
        for item, needle in cases:
            with self.subTest(item=item):
                self.assert_refused(self.click(object_name="qtSkeletonFileButton", menu_item=item), needle)
        self.store._enabled = False
        self.assert_refused(self.click(object_name="qtSkeletonFileButton", menu_item="Save Skeleton"), "disabled")
        self.assert_refused(self.click(object_name="qtPasteButton", menu_item="Save Skeleton"), "no drop-down menu")
        self.assertEqual(sum(a.triggered for a in self.entries), 0)

    def test_a_delete_menu_entry_is_pressed_now(self) -> None:
        delete = fake_qt.Action("Delete Skeleton")
        self.entries.append(delete)
        self.run_click(object_name="qtSkeletonFileButton", menu_item="Delete Skeleton")
        self.assertEqual(delete.triggered, 1)

    def test_owner_exception_wrap_points_menu_entries_in_body_wrap_only(self) -> None:
        save, load = fake_qt.Action("Save Wrap Points"), fake_qt.Action("Load Wrap Points")
        ai, credit = fake_qt.Action("Save AI Points"), fake_qt.Action("Load Wrap Points (1 credit)")
        wp = fake_qt.ToolButton("", self.win, name="qtWrapPointsFileButton")
        wp._tooltip = "Wrap points file"
        wp._menu = fake_qt.ActionMenu([save, load, ai, credit])
        self.run_click(object_name="qtWrapPointsFileButton", menu_item="Save Wrap Points")
        self.run_click(object_name="qtWrapPointsFileButton", menu_item="load wrap points")
        self.assertEqual((save.triggered, load.triggered), (1, 1))
        self.assert_refused(self.click(object_name="qtWrapPointsFileButton", menu_item="Save AI Points"),
                            "mentions 'point'")
        self.assert_refused(self.click(object_name="qtWrapPointsFileButton", menu_item="Load Wrap Points (1 credit)"),
                            "refused")
        paid = fake_qt.Action("Save Wrap Points")
        paid._tooltip = "Uses one credit"
        pay_btn = fake_qt.ToolButton("", self.win, name="qtPaidFileButton")
        pay_btn._menu = fake_qt.ActionMenu([paid])
        self.assert_refused(self.click(object_name="qtPaidFileButton", menu_item="Save Wrap Points"),
                            "mentions 'credit'")
        self.assertEqual(paid.triggered, 0)
        self.assertEqual((ai.triggered, credit.triggered), (0, 0))
        other = self.tool_window("Headshot 3", name="HeadshotWindow")
        hs = fake_qt.ToolButton("", other, name="qtHsFile")
        hs._menu = fake_qt.ActionMenu([fake_qt.Action("Save Wrap Points")])
        self.assert_refused(self.click(window="Headshot 3", object_name="qtHsFile", menu_item="Save Wrap Points"),
                            "mentions 'point'")
        self.assertEqual(hs._menu.actions()[0].triggered, 0)


class JobTest(ClickTestCase):
    def test_the_click_runs_on_a_qt_timer_and_the_picture_comes_after_wait_ms(self) -> None:
        started = self.click(text="Paste", wait_ms=2500)
        self.assertTrue(started["success"], started)
        self.assertTrue(started["job_id"].startswith("click-"))
        fake_qt.drain(1)                                     # the job's first step: schedules the click
        self.assertEqual(fake_qt.Timer.pending_ms(), [cc5_uiclick.CLICK_DELAY_MS, cc5_uiclick.CLICK_DELAY_MS + 2500])
        self.assertEqual(self.paste.clicks, 0)
        result = self.finish(started)
        self.assertEqual((self.paste.clicks, result["waited_ms"]), (1, 2500))

    def test_a_click_that_opens_a_modal_window_is_reported_and_nothing_is_answered(self) -> None:
        opened = []

        def open_modal() -> None:
            dlg = fake_qt.make_dialog(self.q, "Save Skeleton", "File name?", ["Save", "Cancel"])
            dlg._modal = True
            opened.append(dlg)
            fake_qt.drain()                                  # the modal window's own event loop runs the next step

        self.save.on_click = open_modal
        started = self.click(text="Save Skeleton")
        fake_qt.drain()
        job = cc5_ui.ui_job({"job_id": started["job_id"]})
        json.dumps(job)
        result = job["result"]
        self.assertTrue(result["success"], result)
        self.assertFalse(result["click_returned"])
        self.assertIn("has not returned yet", result["note"])
        self.assertEqual([d["title"] for d in result["dialogs"]], ["Save Skeleton"])
        self.assertTrue(result["dialogs"][0]["png_base64"])
        self.assertEqual([b.clicks for b in opened[0].findChildren(fake_qt.PushButton)], [0, 0])

    def test_a_click_that_raises_is_reported(self) -> None:
        def boom() -> None:
            raise RuntimeError("Internal C++ object already deleted")

        self.paste.on_click = boom
        result = self.run_click(text="Paste")
        self.assertFalse(result["success"])
        self.assertIn("RuntimeError", result["error"])
        self.assertTrue(result["click_returned"])

    def test_the_button_is_checked_again_when_the_job_starts(self) -> None:
        started = self.click(text="Paste")
        self.paste._enabled = False                          # greyed out before the job's first step
        result = self.finish(started)
        self.assertFalse(result["success"])
        self.assertIn("disabled", result["error"])
        self.assertEqual(self.paste.clicks, 0)

    def test_toggle_buttons_report_checked_before_and_after(self) -> None:
        toggle = fake_qt.PushButton("Show Mesh", self.win, name="qtShowMesh")
        toggle.isCheckable = lambda: True
        toggle.on_click = lambda: toggle.setChecked(not toggle.isChecked())
        result = self.run_click(object_name="qtShowMesh")
        self.assertEqual((result["checked_before"], result["checked_after"]), (False, True))

    def test_a_window_that_closed_after_the_click_has_no_picture(self) -> None:
        self.paste.on_click = lambda: setattr(self.win, "_visible", False)
        result = self.run_click(text="Paste")
        self.assertFalse(result["window_open"])
        self.assertNotIn("png_base64", result)
        self.assertEqual(self.win.grabbed, 0)

    def test_screenshot_false_returns_no_pictures(self) -> None:
        self.dialog("Note", "Saved.", ["OK"])
        result = self.run_click(text="Paste", screenshot=False)
        self.assertNotIn("png_base64", result)
        self.assertEqual(result["dialogs"][0]["title"], "Note")
        self.assertNotIn("png_base64", result["dialogs"][0])

    def test_one_ui_job_at_a_time(self) -> None:
        cc5_ui.start_job("other", lambda p: {"success": True}, {})
        res = self.click(text="Paste")
        self.assertFalse(res["success"])
        self.assertIn("another UI job", res["error"])


class ArgumentsTest(ClickTestCase):
    def test_bad_requests_are_refused_before_anything_runs(self) -> None:
        bad = (
            {},
            {"window": "Body Wrap"},
            {"window": "", "text": "Paste"},
            {"window": 3, "text": "Paste"},
            {"window": "Body Wrap", "text": ""},
            {"window": "Body Wrap", "text": "Paste", "objectname": "qtPasteButton"},
            {"window": "Body Wrap", "text": "x" * 300},
            {"window": "Body Wrap", "text": "Paste", "screenshot": "yes"},
            {"window": "Body Wrap", "menu_item": "Save Skeleton"},
        )
        for body in bad:
            with self.subTest(body=body):
                self.assertFalse(cc5_uiclick.ui_click(body)["success"])
        self.assertEqual(fake_qt.Timer.singles, [])
        self.assertEqual(self.paste.clicks, 0)

    def test_wait_ms_default_and_limits(self) -> None:
        def wait(value: object = None) -> int:
            body = {"window": "w", "text": "t"}
            if value is not None:
                body["wait_ms"] = value
            return cc5_uiclick.read_args(body)[0]["wait_ms"]

        self.assertEqual(wait(), cc5_uiclick.DEFAULT_WAIT_MS)
        self.assertEqual(wait(999_999), cc5_uiclick.MAX_WAIT_MS)
        self.assertEqual(wait(1), cc5_uiclick.MIN_WAIT_MS)
        self.assertEqual(wait("nope"), cc5_uiclick.DEFAULT_WAIT_MS)

    def test_route(self) -> None:
        self.assertEqual(cc5_uiclick.ROUTES, {"/ui/click": ("ui_click", cc5_uiclick.ui_click)})


if __name__ == "__main__":
    unittest.main()
