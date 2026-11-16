"""Network notifications preserve lazy Cast setup on mobile data."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from felisradio1 import controller

class CastNetworkControllerTests(unittest.TestCase):
    def test_mobile_scan_and_local_selection_do_not_construct_cast_manager(self):
        with patch.object(controller,'_cast',None),patch.object(controller,'_network_epoch',4), \
             patch.object(controller,'_wifi_available',False),patch.object(controller,'_send') as send, \
             patch.object(controller,'CastManager') as factory:
            controller.scan();controller.local(7)
            factory.assert_not_called()
            self.assertEqual(send.call_args_list[0].args,('cast_devices',dict(
                items=[],scanning=False,error=False,networkEpoch=4)))
            self.assertEqual(send.call_args_list[1].args,('local_selected',dict(request=7)))

    def test_only_new_network_generation_reaches_existing_manager(self):
        manager=Mock()
        with patch.object(controller,'_cast',manager),patch.object(controller,'_network_epoch',4), \
             patch.object(controller,'_wifi_available',False):
            controller.network(5,True)
            controller.network(4,False)
            manager.network_changed.assert_called_once_with(5,True)
            self.assertEqual(controller._network_epoch,5)
            self.assertTrue(controller._wifi_available)
