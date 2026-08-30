"""Unit tests for TE1000 runtime ops (target / activate / start / tasks)."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from twincat_automation_interface import TcAutomationInterface


def _make_bridge() -> TcAutomationInterface:
    with patch.object(TcAutomationInterface, "__init__", lambda self: None):
        bridge = TcAutomationInterface.__new__(TcAutomationInterface)
    bridge._dte = None
    bridge._sys_man = None
    bridge._plc_proj_item = None
    bridge._prereqs = {
        "io_disabled_all": False,
        "last_activate_ok": None,
        "last_boot_ok": None,
        "target_net_id": "",
    }
    bridge._msg_baseline = None
    bridge._call_sta = lambda func, *a, timeout=300, **kw: func(*a, **kw)
    return bridge


class TestRuntimeConfirmGuards(unittest.TestCase):
    def test_set_target_requires_confirm(self):
        b = _make_bridge()
        b._sys_man = MagicMock()
        r = b.set_target_net_id("1.2.3.4.1.1", confirm=False)
        self.assertFalse(r.success)
        self.assertEqual(r.error_code, "confirm_required")
        b._sys_man.SetTargetNetId.assert_not_called()

    def test_activate_requires_confirm(self):
        b = _make_bridge()
        b._sys_man = MagicMock()
        r = b.activate_configuration(confirm=False)
        self.assertFalse(r.success)
        self.assertEqual(r.error_code, "confirm_required")
        b._sys_man.ActivateConfiguration.assert_not_called()

    def test_start_requires_confirm(self):
        b = _make_bridge()
        b._sys_man = MagicMock()
        r = b.start_restart_twincat(confirm=False)
        self.assertFalse(r.success)
        self.assertEqual(r.error_code, "confirm_required")
        b._sys_man.StartRestartTwinCAT.assert_not_called()


class TestRuntimeOps(unittest.TestCase):
    def test_no_sysman(self):
        b = _make_bridge()
        self.assertFalse(b.get_target_net_id().success)
        self.assertFalse(b.list_tasks().success)

    def test_get_set_target(self):
        b = _make_bridge()
        sm = MagicMock()
        sm.GetTargetNetId.return_value = "5.80.201.232.1.1"
        b._sys_man = sm
        r = b.get_target_net_id()
        self.assertTrue(r.success)
        self.assertEqual(r.net_id, "5.80.201.232.1.1")

        sm.GetTargetNetId.return_value = "127.0.0.1.1.1"
        r2 = b.set_target_net_id("127.0.0.1.1.1", confirm=True)
        self.assertTrue(r2.success)
        sm.SetTargetNetId.assert_called_once_with("127.0.0.1.1.1")

    def test_activate_and_start(self):
        b = _make_bridge()
        sm = MagicMock()
        sm.IsTwinCATStarted.return_value = True
        b._sys_man = sm
        self.assertTrue(b.activate_configuration(confirm=True).success)
        sm.ActivateConfiguration.assert_called_once()
        r = b.start_restart_twincat(confirm=True)
        self.assertTrue(r.success)
        sm.StartRestartTwinCAT.assert_called_once()

    def test_list_tasks(self):
        b = _make_bridge()
        sm = MagicMock()
        root = MagicMock()
        root.ChildCount = 2
        t1 = MagicMock()
        t1.Name = "PlcTask"
        t1.PathName = "TIRT^PlcTask"
        t1.ItemSubType = 0
        t2 = MagicMock()
        t2.Name = "Task 2"
        t2.PathName = "TIRT^Task 2"
        t2.ItemSubType = 1
        root.Child.side_effect = lambda i: t1 if i == 1 else t2
        sm.LookupTreeItem.return_value = root
        b._sys_man = sm
        r = b.list_tasks()
        self.assertTrue(r.success)
        self.assertEqual(len(r.tasks), 2)
        self.assertEqual(r.tasks[0]["name"], "PlcTask")

    def test_task_info_produce_xml(self):
        b = _make_bridge()
        sm = MagicMock()
        item = MagicMock()
        item.Name = "PlcTask"
        item.PathName = "TIRT^PlcTask"
        item.ItemSubType = 0
        item.ProduceXml.return_value = (
            '<?xml version="1.0"?>'
            "<TreeItem><ItemName>PlcTask</ItemName>"
            "<TaskDef><CycleTime>100000</CycleTime>"
            "<Priority>20</Priority></TaskDef></TreeItem>"
        )
        sm.LookupTreeItem.return_value = item
        b._sys_man = sm
        r = b.get_task_info("PlcTask")
        self.assertTrue(r.success)
        self.assertEqual(r.task.get("cycle_time"), "100000")
        self.assertEqual(r.task.get("priority"), "20")
        sm.LookupTreeItem.assert_called_with("TIRT^PlcTask")

    def test_io_set_disabled_requires_confirm(self):
        b = _make_bridge()
        b._sys_man = MagicMock()
        r = b.set_io_disabled(path="TIID^Dev", disabled=True, confirm=False)
        self.assertFalse(r.success)
        b._sys_man.LookupTreeItem.assert_not_called()

    def test_list_and_disable_io(self):
        b = _make_bridge()
        sm = MagicMock()
        root = MagicMock()
        root.ChildCount = 1
        dev = MagicMock()
        dev.Name = "Device 1 (RT-Ethernet Protocol)"
        dev.PathName = "TIID^Device 1 (RT-Ethernet Protocol)"
        dev.ItemSubType = 0
        dev.Disabled = 0
        root.Child.side_effect = lambda i: dev
        item = MagicMock()
        item.Disabled = 0

        def _lookup(path):
            if path == "TIID":
                return root
            return item

        sm.LookupTreeItem.side_effect = _lookup
        b._sys_man = sm

        listed = b.list_io_devices()
        self.assertTrue(listed.success)
        self.assertEqual(listed.devices[0]["name"], "Device 1 (RT-Ethernet Protocol)")
        self.assertFalse(listed.devices[0]["disabled"])

        item.Disabled = 0
        r = b.set_io_disabled(
            path="Device 1 (RT-Ethernet Protocol)",
            disabled=True,
            confirm=True,
        )
        self.assertTrue(r.success)
        self.assertEqual(item.Disabled, 1)
        self.assertTrue(r.disabled)

        r_all = b.set_io_disabled(all_devices=True, disabled=True, confirm=True)
        self.assertTrue(r_all.success)
        self.assertEqual(len(r_all.changed), 1)


if __name__ == "__main__":
    unittest.main()
