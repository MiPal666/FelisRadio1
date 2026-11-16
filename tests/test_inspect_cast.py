"""The comparison probe must never launch a receiver or send player controls."""
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from inspect_cast import inspect_connected, MEDIA_NAMESPACE

class InspectCastTests(unittest.TestCase):
    def cast(self,namespaces):
        media=Mock()
        media.status=NS(content_id='https://example.invalid/radio',content_type='audio/aac',
                        stream_type='LIVE',player_state='PLAYING')
        return NS(socket_client=NS(app_namespaces=namespaces),
                  status=NS(app_id='CUSTOM_APP',display_name='Replaio'),media_controller=media)

    def test_only_sends_get_status_without_autolaunch(self):
        cast=self.cast([MEDIA_NAMESPACE])
        def reply(message,callback_function): callback_function(True,{'type':'MEDIA_STATUS','status':[{'media':{'contentId':'full-url'}}]})
        cast.media_controller.send_message_nocheck.side_effect=reply
        result=inspect_connected(cast)
        self.assertEqual(result['status_request'],'ok')
        self.assertEqual(result['receiver_app_id'],'CUSTOM_APP')
        self.assertEqual(result['content_type'],'audio/aac')
        self.assertEqual(result['media_status_response']['status'][0]['media']['contentId'],'full-url')
        self.assertEqual(cast.media_controller.method_calls[0].args,({'type':'GET_STATUS'},))
        self.assertEqual([call[0] for call in cast.media_controller.method_calls],['send_message_nocheck'])

    def test_missing_namespace_never_launches_receiver(self):
        cast=self.cast(['custom'])
        result=inspect_connected(cast)
        self.assertEqual(result['status_request'],'unsupported_namespace')
        self.assertEqual(cast.media_controller.method_calls,[])

    def test_timeout_never_retries_or_controls_playback(self):
        cast=self.cast([MEDIA_NAMESPACE])
        result=inspect_connected(cast,timeout=0)
        self.assertEqual(result['status_request'],'timeout')
        self.assertEqual([call[0] for call in cast.media_controller.method_calls],['send_message_nocheck'])
